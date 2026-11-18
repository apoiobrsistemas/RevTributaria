# Agente Validador: Guardião da Legislação Oficial & Vigia
Ative `official_law_scraper`.

## Checklist de Validação
1. Verifique se o validador de domínio bloqueia qualquer URL fora de `.gov.br`, `.leg.br`, `.jus.br` ou `.mp.br`.
2. Confirme que chamadas de LLM para extração de regras NÃO possuem web search habilitado e utilizam `response_schema` JSON.
3. Valide a função de conferência literal de citações (normalização sem acento/pontuação/lowercase).
4. Verifique se o Vigia Noturno utiliza os mesmos extratores (`playwright`, `openpyxl`, `python-docx`, `pypdf`) da ingestão inicial.