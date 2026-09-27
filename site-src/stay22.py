"""Static, bounded affiliate links. No network, JavaScript, tracker or iframe."""
import html
import json
from pathlib import Path
from urllib.parse import quote, urlencode

AID = 'voyagesansdetourfr'
ENDPOINT = 'https://www.stay22.com/allez/booking'
ORIGIN = 'https://voyagesansdetour.fr'
PREVIEW_ORIGIN = 'http://127.0.0.1:8770'
DESTINATIONS = {
    'lisbonne': {'url': 'https://www.booking.com/city/pt/lisbon.fr.html', 'campaign': 'vsdlisbonne'},
    'porto': {'url': 'https://www.booking.com/city/pt/porto.fr.html', 'campaign': 'vsdporto'},
}
GUIDES = {'lisbonne-3-jours-sans-voiture': 'lisbonne', 'ou-dormir-lisbonne-quartiers': 'lisbonne',
          'porto-3-jours-sans-voiture': 'porto'}


def validate_config(config):
    keys = {'schema_version', 'enabled', 'hosting_verified', 'links_verified', 'aid',
            'endpoint', 'lang', 'currency', 'roam', 'destinations'}
    if not isinstance(config, dict) or set(config) != keys:
        raise ValueError('Stay22 : configuration incomplète ou champ non autorisé.')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Stay22 : version de configuration invalide.')
    if any(type(config[name]) is not bool for name in ('enabled', 'hosting_verified', 'links_verified', 'roam')):
        raise ValueError('Stay22 : validations booléennes requises.')
    if (config['aid'] != AID or config['endpoint'] != ENDPOINT or config['lang'] != 'fr' or
            config['currency'] != 'EUR' or config['roam'] is not False or config['destinations'] != DESTINATIONS):
        raise ValueError('Stay22 : AID, URL, destination ou paramètre non validé.')
    if config['enabled'] and not (config['hosting_verified'] and config['links_verified']):
        raise ValueError('Stay22 : activation refusée sans validation de l’hébergement et des liens.')
    return config


def load_config(path):
    return validate_config(json.loads(Path(path).read_text(encoding='utf-8')))


def is_active(config, *, public, origin):
    validate_config(config)
    if config['enabled'] and (not public or origin != ORIGIN):
        raise ValueError('Stay22 : activation autorisée uniquement pour le domaine public prévu.')
    return config['enabled']


def validate_preview(root, out, *, public, origin):
    root, out = Path(root).resolve(), Path(out)
    expected = root / 'previews/stay22/site'
    if (public or origin != PREVIEW_ORIGIN or out.resolve() != expected or
            any(path.is_symlink() for path in (root / 'previews', root / 'previews/stay22', out))):
        raise ValueError('Stay22 : aperçu réservé au dossier isolé previews/stay22/site et à localhost, jamais public/.')


def booking_url(config, destination):
    validate_config(config)
    if destination not in DESTINATIONS:
        raise ValueError('Stay22 : destination non autorisée.')
    target = config['destinations'][destination]
    return ENDPOINT + '?' + urlencode({'aid': config['aid'], 'link': target['url'], 'campaign': target['campaign'],
                                      'lang': 'fr', 'currency': 'EUR', 'roam': 'false'}, quote_via=quote)


def guide_box(config, slug, *, active=False, preview=False):
    validate_config(config)
    if active and preview:
        raise ValueError('Stay22 : aperçu et lien actif sont incompatibles.')
    if (not active and not preview) or slug not in GUIDES:
        return ''
    if active and not config['enabled']:
        raise ValueError('Stay22 : encart actif demandé avec une configuration inactive.')
    city = GUIDES[slug].title()
    label = f'Voir les hébergements à {city} →'
    cta = (f'<a class="stay22-cta" href="{html.escape(booking_url(config, GUIDES[slug]), quote=True)}" '
           f'target="_blank" rel="sponsored nofollow noopener noreferrer">{label}</a>') if active else (
           f'<span class="stay22-cta" role="link" aria-disabled="true">{label}</span>')
    preview_note = '<p class="stay22-preview-note">Aperçu local · Le lien de réservation est désactivé dans cet aperçu.</p>' if preview else ''
    return f'''<section id="hebergement" class="stay22-box" aria-labelledby="stay22-title"><span class="stay22-kicker">Pour préparer la suite</span><h2 id="stay22-title">Un hébergement à {city} ?</h2><p>Comparez les hébergements sur Booking.com pour les dates de votre séjour. Nous n’avons pas testé les établissements listés.</p>{cta}<p class="stay22-disclosure">Lien affilié via Stay22 : une réservation peut nous apporter une commission, selon les conditions du partenaire. Vérifiez le prix total, l’emplacement et les conditions de réservation sur Booking.com.</p>{preview_note}</section>'''


CSS = '''<style id="stay22-style">.stay22-box{margin:38px 0;padding:25px 28px;border:1px solid #ccd6e9;border-radius:12px;background:#f4f6fc}.stay22-box .stay22-kicker{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#214fe6}.article-body .stay22-box h2{font-size:27px;line-height:1.2;margin:10px 0 14px}.stay22-box p{line-height:1.7}.stay22-box .stay22-cta{display:inline-block;margin:4px 0 8px;font-size:14px;font-weight:700;line-height:1.5;color:#214fe6;text-decoration:underline;text-underline-offset:4px}.stay22-box .stay22-disclosure,.stay22-preview-note{font-size:12px;line-height:1.65;color:#596575;margin:10px 0 0}.stay22-preview-note{font-weight:700}.stay22-cta[aria-disabled]{cursor:default}.stay22-preview-banner{padding:14px 18px;border:1px solid #214fe6;border-radius:8px;background:#eef2ff;color:#183580;font-size:13px;margin:16px 0}@media(max-width:600px){.stay22-box{padding:21px 20px}.article-body .stay22-box h2{font-size:24px}}</style>'''

TRANSPARENCY = '''<h2>Les liens d’hébergement</h2><p>Trois guides proposent un lien affilié vers Booking.com, via Stay22. Une mention apparaît près de chaque lien. Une réservation peut donner lieu à une commission selon les conditions du partenaire ; aucun revenu n’est garanti et aucun versement n’est annoncé ici.</p><p>Nous n’avons pas testé les établissements listés. La présence d’un lien rémunéré ne vaut pas recommandation personnelle d’un hôtel. Les tarifs, disponibilités et conditions restent à vérifier chez le vendeur.</p><h2>Publicité et indépendance</h2><p>Aucune publicité d’affichage n’est activée. Les liens vers les transports, monuments et organismes touristiques restent des liens informatifs ordinaires. Les relations commerciales, produits offerts et placements seront identifiés.</p>'''
PRIVACY = '''<h2>Liens affiliés vers les hébergements</h2><p>Les liens signalés « Lien affilié via Stay22 » sont des liens HTML ordinaires. Aucun script, iframe ou pixel Stay22 n’est chargé par le blog à l’ouverture d’une page, et aucune connexion automatique vers Stay22 ou Booking.com n’est ajoutée pour ces encarts.</p><p>Si vous choisissez d’ouvrir un lien, votre navigateur contacte Stay22 pour la redirection, puis Booking.com. Ces services peuvent recevoir des données techniques comme votre adresse IP et votre navigateur, et traiter l’attribution d’une éventuelle réservation selon leurs propres politiques de confidentialité. La mesure d’audience facultative du blog reste un choix distinct ; accepter Analytics n’active pas un script d’affiliation.</p>'''
