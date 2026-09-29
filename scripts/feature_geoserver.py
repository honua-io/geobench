"""GeoServer's explicit OGC sorting contract, checked outside measured traffic."""
import base64
import hashlib
import json
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SORTING_CONFORMANCE = 'http://www.opengis.net/spec/ogcapi-records-1/1.0/req/sorting'


def _settings(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError('Malformed GeoServer WFS settings') from exc
    if root.tag != 'wfs' or len(root.findall('metadata')) > 1:
        raise ValueError('Unexpected GeoServer WFS settings')
    entries = root.findall("metadata/entry[@key='ogcapiFeatures']")
    if len(entries) > 1:
        raise ValueError('Ambiguous GeoServer feature conformance settings')
    if entries and (len(entries[0]) != 1 or entries[0][0].tag != 'ogcapiFeatures'):
        raise ValueError('Unexpected GeoServer feature conformance metadata type')
    node = entries[0][0] if entries else None
    if node is not None and len(node.findall('sortBy')) > 1:
        raise ValueError('Ambiguous GeoServer sorting configuration')
    return root, node


def enable_sorting_settings(xml):
    """Preserve unrelated settings; use GeoServer's registered typed metadata."""
    root, node = _settings(xml)
    if node is None:
        metadata = root.find('metadata')
        if metadata is None:
            metadata = ET.SubElement(root, 'metadata')
        entry = ET.SubElement(metadata, 'entry', key='ogcapiFeatures')
        node = ET.SubElement(entry, 'ogcapiFeatures')
    sorting = node.find('sortBy')
    if sorting is None:
        sorting = ET.SubElement(node, 'sortBy')
    sorting.text = 'true'
    return ET.tostring(root, encoding='utf-8')


def sorting_receipt(xml, advertisement):
    """Fail closed if either persisted or advertised support is absent."""
    _, node = _settings(xml)
    if node is None or node.findtext('sortBy', '').strip() != 'true':
        raise ValueError('GeoServer must explicitly enable OGC query sorting')
    classes = advertisement.get('conformsTo') if isinstance(advertisement, dict) else None
    if not isinstance(classes, list) or not all(isinstance(item, str) for item in classes) or SORTING_CONFORMANCE not in classes:
        raise ValueError('GeoServer does not advertise required sorting conformance')
    return {'sort_by': True, 'sorting_conformance': SORTING_CONFORMANCE,
            'conforms_to': sorted(set(classes)), 'wfs_settings_sha256': hashlib.sha256(xml).hexdigest()}


def geoserver_sorting(base, password, configure=False):
    """Configure fresh owned stacks only; reused stacks and final checks are read-only."""
    settings_url = base + '/geoserver/rest/services/wfs/settings.xml'
    headers = {'Authorization': 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode(),
               'Accept': 'application/xml'}
    def read_settings():
        with urlopen(Request(settings_url, headers=headers), timeout=30) as response:
            return response.read()
    xml = read_settings()
    if configure:
        updated = enable_sorting_settings(xml)
        request = Request(settings_url, data=updated, method='PUT',
                          headers={**headers, 'Content-Type': 'application/xml'})
        with urlopen(request, timeout=30):
            pass
        xml = read_settings()
    request = Request(base + '/geoserver/ogc/features/v1/conformance?f=json',
                      headers={'Accept': 'application/json'})
    with urlopen(request, timeout=30) as response:
        advertisement = json.load(response)
    return sorting_receipt(xml, advertisement)
