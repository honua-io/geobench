// Pure functions shared by preflight and every measured response; also tested in Node.
export function validateFeatureResponse(payload, expected, protocol, fields) {
  if (!payload || !Array.isArray(payload.features) || payload.error ||
      (protocol === 'ogc' && payload.type !== 'FeatureCollection')) return 'missing feature collection';
  if (payload.features.length !== expected.features.length) return 'wrong feature count';
  if (payload.numberReturned !== undefined && payload.numberReturned !== expected.features.length) return 'wrong numberReturned';
  if (payload.numberMatched !== undefined && payload.numberMatched !== expected.matched) return 'wrong numberMatched';
  if (payload.crs && !['urn:ogc:def:crs:OGC:1.3:CRS84', 'urn:ogc:def:crs:EPSG::4326', 'EPSG:4326'].includes(payload.crs.properties && payload.crs.properties.name)) return 'wrong CRS';
  if (payload.spatialReference && payload.spatialReference.wkid !== 4326) return 'wrong CRS';
  const ids = new Set();
  for (let i = 0; i < payload.features.length; i++) {
    const feature = payload.features[i];
    if (!feature || (protocol === 'ogc' && feature.type !== 'Feature')) return 'malformed feature';
    const properties = protocol === 'ogc' ? feature.properties : feature.attributes;
    if (!properties || typeof properties !== 'object') return 'missing attributes';
    if (Object.keys(properties).some(k => k !== 'id' && !fields.includes(k))) return 'unexpected attribute';
    let id = properties.id;
    if (id === undefined && protocol === 'ogc') {
      const match = String(feature.id).match(/^(?:bench_points\.)?(\d+)$/);
      id = match ? Number(match[1]) : undefined;
    }
    const row = expected.features[i];
    if (protocol === 'ogc') {
      const match = String(feature.id).match(/^(?:bench_points\.)?(\d+)$/);
      if (!match || Number(match[1]) !== row.id) return 'wrong feature ID';
    }
    if (typeof id !== 'number' || id !== row.id || ids.has(id)) return 'wrong ID sequence';
    ids.add(id);
    for (const field of fields) {
      const value = properties[field];
      const want = row[field];
      if (field === 'created_at' || field === 'updated_at') {
        if (protocol === 'ogc' && typeof value !== 'string') return 'wrong date type';
        if (protocol === 'gsr' && typeof value !== 'number') return 'wrong date type';
        if (new Date(value).getTime() !== new Date(want).getTime()) return 'wrong date';
      } else if (typeof value !== typeof want || value !== want) return 'wrong attribute: ' + field;
    }
    const geometry = feature.geometry;
    const coordinates = protocol === 'ogc' ? geometry && geometry.coordinates : geometry && [geometry.x, geometry.y];
    if (!geometry || (protocol === 'ogc' && geometry.type !== 'Point') ||
        !Array.isArray(coordinates) || coordinates.length !== 2) return 'wrong geometry type';
    if (protocol === 'gsr' && geometry.spatialReference && ![4326].includes(geometry.spatialReference.wkid)) return 'wrong CRS';
    for (let axis = 0; axis < 2; axis++) {
      if (typeof coordinates[axis] !== 'number' || !Number.isFinite(coordinates[axis]) ||
          Math.abs(coordinates[axis] - row.geometry.coordinates[axis]) > 1e-7) return 'wrong geometry';
    }
  }
  return null;
}
