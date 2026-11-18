---
name: official_law_scraper
description: Coleta blindada de legislação em sites oficiais (.gov.br/.leg.br), recortes de vigência, validação literal de citações da IA e Vigia Noturno em Python.
---

# Coleta Oficial e Vigia da Legislação

## Guardrails Invioláveis
- **Whitelist de Domínios**: Regex estrita `^https?://[^/]+\.(gov|leg|jus|mp)\.br(/|$)`. Qualquer URL fora disso gera exceção imediata.
- **LLM Sem Busca Web**: Ao extrair regras via API de IA, nunca habilitar web search. Enviar apenas o texto recortado da norma oficial + NCM/CEST com pontos (`8517.13.00`, `21.053.01`).
- **Validação Literal de Citação**: Normalizar texto oficial e trecho citado (`unicodedata.normalize('NFKD')`, remover acentos/pontuação, `.lower()`). Descartar qualquer fonte cujo trecho não seja substring exata do texto baixado.
- **Falha Segura em Recortes**: Se o marcador de início do artigo/anexo não for encontrado na página baixada, abortar a leitura daquela norma (nunca enviar texto revogado ou página inteira).

## Vigia Noturno (Python CLI / Agendador — Zero IA)
- Executa diariamente:
  1. Rebaixa normas oficiais usando os mesmos extratores (`BeautifulSoup` isolando o corpo da lei, `pypdf`, `python-docx`, `openpyxl` para TIPI e `playwright` headless para portais como SEFAZ-RJ).
  2. Compara SHA-256 do corpo limpo e verifica se todas as citações vigentes continuam presentes.
  3. Verifica alterações na planilha TIPI (alíquotas e linhas de `Ex`) e regras de IBS/CBS.
  4. Abre alerta `VIGIA-AAAAMMDD-UF-GRUPO` quando houver mudança ou falha de acesso >= 2 dias.