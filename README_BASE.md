# ComprovanteIA — Base consolidada de comprovantes

Esta base é 100% fictícia e foi criada para uma PoC educacional.

## Formato

A estrutura simula o cenário em que os comprovantes ficam organizados por:
Ano → Mês → Dia → PDF consolidado.

Cada PDF contém vários comprovantes, sendo que cada comprovante ocupa uma página.

Exemplo:

2026/
└── 09-SETEMBRO/
    ├── 01-09/
    │   └── pagamentos_01-09-2026.pdf
    ├── 02-09/
    │   └── pagamentos_02-09-2026.pdf
    └── ...

O índice `indice_comprovantes_ficticios.csv` informa, para cada comprovante:
- empresa pagadora
- fornecedor
- data
- nota fiscal
- valor
- forma de pagamento
- arquivo PDF
- página do comprovante

Isso permitirá que a aplicação encontre não apenas o PDF, mas a página exata
onde o comprovante está.

## Exemplo de consulta

"Preciso do comprovante da Empresa Alfa referente à NF-202600123."

Resultado esperado:
Arquivo: pagamentos_18-09-2026.pdf
Página: 4

Todos os nomes, CNPJs, notas fiscais, valores, bancos e códigos de autenticação
são fictícios.
