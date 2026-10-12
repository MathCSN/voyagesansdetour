"""One bounded, manual Workers AI connectivity/quality probe; never publishes."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import urllib.error

ACCOUNT = '6f1926fc39a2e010e9cb86d0e195c28c'
MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'
ENDPOINT = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}'
HARD_STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=dt.timezone.utc)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def run():
    from quota_policy import hold as quota_hold
    now = dt.datetime.now(dt.timezone.utc)
    report = {'observedAt': now.isoformat(), 'model': MODEL, 'accountId': ACCOUNT,
              'publicationAttempted': False, 'maxOutputTokens': 256, 'maxCalls': 1,
              'status': 'not_called'}
    if now > HARD_STOP:
        report['status'] = 'authorization_period_ended'
        return report
    budget=quota_hold(now,ACCOUNT)
    if budget:
        report.update(budget)
        return report
    token = os.environ.get('CLOUDFLARE_WORKERS_AI_TOKEN', '')
    if not token:
        report['status'] = 'missing_secret'
        return report
    # Only editorial style is tested here: no travel facts or personal data.
    payload = {'messages': [
        {'role': 'system', 'content': 'Tu écris en français pour Voyage Sans Détour. Ne prétends jamais avoir voyagé ou testé une adresse. Réponds uniquement à la consigne.'},
        {'role': 'user', 'content': 'Rédige en deux phrases une introduction chaleureuse expliquant que nos guides aident à préparer un voyage grâce à des sources officielles. Aucune destination, aucun prix, aucune promesse de résultat.'}],
        'max_tokens': 256, 'temperature': 0.2, 'stream': False}
    body = json.dumps(payload).encode()
    report['requestSha256'] = hashlib.sha256(body).hexdigest()
    report['requestBytes'] = len(body)
    request = urllib.request.Request(ENDPOINT, data=body, method='POST', headers={
        'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
    try:
        # No retries: a timeout may follow a consumed inference.
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=90) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('oversize')
            data = json.loads(raw)
        result = data.get('result', {})
        text = result.get('response')
        if data.get('success') is not True or not isinstance(text, str) or not text.strip():
            raise ValueError('invalid_result')
        if token in text:
            raise ValueError('secret_in_output')
        report.update(status='inference_verified', response=text[:8000])
        usage = result.get('usage', {})
        report['usage'] = {k: v for k, v in usage.items()
                           if k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                           and type(v) is int and v >= 0}
    except urllib.error.HTTPError as error:
        report.update(status='provider_error', httpStatus=error.code)
    except Exception as error:
        report.update(status='unverified_no_retry', errorType=type(error).__name__)
    return report

if __name__ == '__main__':
    report = run()
    Path(os.environ['REPORT_PATH']).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'publicationAttempted')}))
    raise SystemExit(0 if report['status'] == 'inference_verified' else 1)
