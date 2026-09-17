"""Faturas e borderôs de ÁGUA (Saneago e concessionárias municipais de Goiás).

Segundo serviço do app, ao lado da energia, com a mesma arquitetura: extratores por fornecedor → esquema canônico ÚNICO
(`schema_agua`, todas as concessionárias nas mesmas abas/tabelas) → derivados (conta canônica, validação, cruzamento
borderô × analítica) → planilha Excel (app/CLI) ou banco PostgreSQL (servidor/bot).

Os extratores foram portados do repositório `MatheusBraga1106/ProjetoAutoma--oFatura` (Matheus Braga, TJGO), que fez o
levantamento de layouts e os regexes originais de cada concessionária; aqui eles rodam sobre o texto em layout de colunas
do próprio PDF (ou do OCR posicional) em vez de arquivos .txt do pdftotext.
"""
