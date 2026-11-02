export const applyXmlAutofill = (form: Record<string, any>, values: Record<string, string>, previous: Record<string, string>, automatic: Record<string, string> = {}) => {
  const applied: Record<string, string> = {}
  for (const [field, value] of Object.entries(values)) {
    if (value && (!form[field] || form[field] === previous[field] || form[field] === automatic[field])) {
      form[field] = value
      applied[field] = value
    }
  }
  return applied
}

export const clearXmlAutofill = (form: Record<string, any>, previous: Record<string, string>, defaults: Record<string, string> = {}) => {
  for (const [field, value] of Object.entries(previous)) {
    if (form[field] === value) form[field] = defaults[field] || ''
  }
}
