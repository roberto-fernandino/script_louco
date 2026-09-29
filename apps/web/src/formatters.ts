function digits(value: unknown): string {
  return String(value ?? "").replace(/\D/g, "");
}

export function formatValue(key: string, value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (typeof value !== "string" && typeof value !== "number") return String(value);

  const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, "");
  const raw = digits(value);
  if (normalizedKey.includes("cpf") || (normalizedKey.includes("document") && raw.length === 11)) {
    return raw.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4") || String(value);
  }
  if (normalizedKey.includes("cnpj") || (normalizedKey.includes("document") && raw.length === 14)) {
    return raw.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") || String(value);
  }
  if (normalizedKey === "cep" || normalizedKey.includes("postalcode") || normalizedKey.includes("zipcode")) {
    return digits(value).replace(/^(\d{5})(\d{3})$/, "$1-$2") || String(value);
  }
  if (normalizedKey.includes("phone") || normalizedKey.includes("telefone") || normalizedKey.includes("celular") || normalizedKey.includes("mobile")) {
    const raw = digits(value);
    if (raw.length === 11) return raw.replace(/^(\d{2})(\d{5})(\d{4})$/, "($1) $2-$3");
    if (raw.length === 10) return raw.replace(/^(\d{2})(\d{4})(\d{4})$/, "($1) $2-$3");
  }
  return String(value);
}
