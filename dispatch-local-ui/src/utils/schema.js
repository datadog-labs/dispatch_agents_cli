// Generates a concrete example object from a JSON Schema, used to pre-fill
// the invoke/send-event payload textarea. Handles Pydantic-emitted schemas:
// defaults, enums, const, oneOf/anyOf/allOf, and nested objects/arrays.
export function generateExampleFromSchema(schema) {
  if (!schema || typeof schema !== 'object') return { message: 'Hello from UI!' };
  const fromProp = (prop, key = 'value') => {
    if (prop.default !== undefined) return prop.default;
    if (prop.enum?.length > 0) return prop.enum[0];
    if (prop.const !== undefined) return prop.const;
    const subSchema = prop.oneOf?.[0] || prop.anyOf?.[0] || prop.allOf?.[0];
    if (subSchema) return fromProp(subSchema, key);
    if (prop.$ref) return null;
    if (prop.type === 'string') return prop.example || `example_${key}`;
    if (prop.type === 'number' || prop.type === 'integer') return prop.example || 0;
    if (prop.type === 'boolean') return prop.example !== undefined ? prop.example : true;
    if (prop.type === 'array') return [prop.items ? fromProp(prop.items, 'item') : 'item'];
    if (prop.type === 'object') return prop.properties ? fromProps(prop.properties) : {};
    return prop.example ?? `example_${key}`;
  };
  const fromProps = (props) => {
    const result = {};
    for (const [key, prop] of Object.entries(props)) result[key] = fromProp(prop, key);
    return result;
  };
  if (schema.properties) return fromProps(schema.properties);
  if (schema.example) return schema.example;
  return { message: 'Hello from UI!' };
}
