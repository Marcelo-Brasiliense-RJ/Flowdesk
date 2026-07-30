"""Conversas de demonstração: o diálogo real que originaria cada automação.

Só dados. Quem monta as mensagens (com timestamps, bloco flowdesk-actions e
ações aprovadas) é o seed_demo.add_chat.

Formato por automação:
  pedido       fala inicial do usuário, do jeito que a pessoa escreveria
  contexto     frase curta do assistente antes de abrir a entrevista
  perguntas    [{id, label, options, recommended, resposta}] — a entrevista
  montagem     o que o assistente narra ao entregar o código (números concretos)
  ajuste_user  o problema real que aparece no primeiro uso
  ajuste_ia    a resposta do assistente + o que ele mudou no código
  patch        trecho de código citado no ajuste (opcional)
  fecho_user   última fala do usuário
  fecho_ia     fechamento do assistente
"""

CONVERSAS = {
    "conciliacao-cartoes": {
        "pedido": "toda segunda eu abro o relatório de vendas do sistema e o extrato da "
        "operadora e fico conferindo linha por linha o que caiu e o que não caiu. "
        "leva quase a manhã inteira. dá pra automatizar isso?",
        "contexto": "Dá sim, e esse é um caso clássico: duas listas que deveriam bater e "
        "quase nunca batem. Só preciso entender quatro coisas antes de montar.",
        "perguntas": [
            {
                "id": "chave",
                "label": "O que identifica a mesma transação nas duas planilhas?",
                "options": ["NSU da transação", "Data + valor", "Número do pedido"],
                "recommended": "NSU da transação",
                "resposta": "NSU da transação",
            },
            {
                "id": "valor",
                "label": "Quando o valor bater diferente entre as duas, o que você quer ver?",
                "options": [
                    "A diferença de cada uma, para eu conferir",
                    "Só a lista, sem a diferença",
                ],
                "recommended": "A diferença de cada uma, para eu conferir",
                "resposta": "A diferença de cada uma, para eu conferir",
            },
            {
                "id": "saida",
                "label": "Como você prefere receber o resultado?",
                "options": [
                    "Uma planilha com uma aba por situação",
                    "Uma planilha só, com uma coluna de situação",
                    "Um resumo na tela",
                ],
                "recommended": "Uma planilha com uma aba por situação",
                "resposta": "Uma planilha com uma aba por situação",
            },
            {
                "id": "gatilho",
                "label": "E quando isso deve rodar?",
                "options": ["Eu envio os arquivos quando precisar", "Toda segunda, automático"],
                "recommended": "Eu envio os arquivos quando precisar",
                "resposta": "Eu envio os arquivos quando precisar",
            },
        ],
        "montagem": "Li os dois arquivos que você anexou: 148 linhas nas vendas (NSU, Data, "
        "Valor, Bandeira) e 151 no extrato da operadora. Cruzei pelo NSU e o resultado do "
        "teste foi: 143 conciliadas, 5 vendas que não apareceram no extrato, 8 lançamentos "
        "da operadora sem venda correspondente e 3 com valor diferente.\n\n"
        "Montei assim: você envia as duas planilhas, o script cruza e devolve um arquivo "
        "com três abas separadas, uma para cada situação. O que não bate fica isolado, "
        "então você olha só o que precisa de decisão.",
        "ajuste_user": "rodei com o arquivo de março e apareceu um monte de divergência "
        "falsa. vi aqui que são as vendas parceladas, o mesmo NSU aparece uma vez na venda "
        "e várias no extrato, uma por parcela",
        "ajuste_ia": "Boa pegada, é isso mesmo. Do jeito que estava, cada parcela virava "
        "uma linha órfã. Ajustei para somar as parcelas do mesmo NSU antes de comparar: "
        "aí a venda de R$ 900 em 3x fecha com os três lançamentos de R$ 300.",
        "patch": "# soma as parcelas do mesmo NSU antes de comparar\n"
        "df_operadora = df_operadora.groupby(\"_chave\", as_index=False).agg(\n"
        "    {\"Valor\": \"sum\", \"NSU\": \"first\"}\n)",
        "fecho_user": "agora fechou certinho, testei com março e abril. pode publicar",
        "fecho_ia": "Publicado. O time acessa em **/app/conciliacao-cartoes** e é só enviar "
        "as duas planilhas. Se um dia a operadora mudar o nome das colunas, o script avisa "
        "em vez de dar resultado errado.",
    },
    "valida-nfe": {
        "pedido": "recebo todo mês um zip com os xml das notas dos clientes. preciso "
        "conferir se as chaves de acesso são válidas e somar os totais por emitente, "
        "hoje faço isso abrindo nota por nota",
        "contexto": "Consigo resolver isso. Antes de escrever, me diga o que você espera "
        "encontrar nesse lote.",
        "perguntas": [
            {
                "id": "escopo",
                "label": "O que precisa ser validado em cada nota?",
                "options": [
                    "Só o dígito verificador da chave",
                    "Chave, CNPJ do emitente e valor total",
                    "Tudo isso mais a situação na SEFAZ",
                ],
                "recommended": "Chave, CNPJ do emitente e valor total",
                "resposta": "Chave, CNPJ do emitente e valor total",
            },
            {
                "id": "sefaz",
                "label": "Consultar a SEFAZ exige certificado digital instalado no servidor. "
                "Seguimos sem a consulta por enquanto?",
                "options": ["Sim, sem consulta por ora", "Não, preciso da consulta"],
                "recommended": "Sim, sem consulta por ora",
                "resposta": "Sim, sem consulta por ora",
            },
            {
                "id": "invalida",
                "label": "Quando a nota vier com problema, o que faço com ela?",
                "options": [
                    "Marcar na planilha e seguir com as outras",
                    "Parar tudo e avisar",
                ],
                "recommended": "Marcar na planilha e seguir com as outras",
                "resposta": "Marcar na planilha e seguir com as outras",
            },
        ],
        "montagem": "Abri o zip de exemplo: 213 XMLs. Recalculei o dígito verificador de "
        "cada chave pelo módulo 11 (é a mesma conta que a SEFAZ faz) e extraí número, "
        "emissão, CNPJ do emitente e o vNF do total.\n\n"
        "Resultado do teste: 212 notas válidas, 1 com chave inconsistente (arquivo "
        "`nfe_00187.xml`) e R$ 1.842.390,55 somados. A nota problemática entra na planilha "
        "marcada como inválida, não trava o lote.",
        "ajuste_user": "e se vier um xml de cancelamento junto no zip? não pode entrar na soma",
        "ajuste_ia": "Faz sentido. Passei a ler o `tpNF` e a situação do evento: nota "
        "cancelada entra na planilha numa aba separada e fica fora do total. Assim você "
        "continua vendo que ela existe, sem contaminar o somatório.",
        "patch": None,
        "fecho_user": "beleza, publica",
        "fecho_ia": "No ar em **/app/valida-nfe**. O lote de agosto já pode subir por lá.",
    },
    "confere-folha": {
        "pedido": "todo mês eu comparo a folha com a do mês anterior no olho pra ver quem "
        "variou muito. com 300 pessoas isso é desumano e sempre escapa alguém",
        "contexto": "Entendi, e aqui o detalhe importante é o que conta como variação. "
        "Três perguntas.",
        "perguntas": [
            {
                "id": "base",
                "label": "Comparo qual valor?",
                "options": ["Líquido a receber", "Salário base", "Total de proventos"],
                "recommended": "Líquido a receber",
                "resposta": "Líquido a receber",
            },
            {
                "id": "limite",
                "label": "A partir de quanto de variação você quer ser avisado?",
                "options": ["5%", "10%", "Eu escolho na hora de rodar"],
                "recommended": "Eu escolho na hora de rodar",
                "resposta": "Eu escolho na hora de rodar",
            },
            {
                "id": "movimento",
                "label": "E quem entrou ou saiu no mês, entra no relatório?",
                "options": [
                    "Sim, em abas separadas",
                    "Não, só quem estava nos dois meses",
                ],
                "recommended": "Sim, em abas separadas",
                "resposta": "Sim, em abas separadas",
            },
        ],
        "montagem": "Comparei os dois arquivos de junho e julho: 312 colaboradores no mês "
        "atual, 309 no anterior. Casei pela matrícula (nome muda, matrícula não).\n\n"
        "No teste saíram 11 pessoas acima de 10% de variação, 6 admitidos e 3 desligados. "
        "O limite virou campo do formulário, então em mês de dissídio você pode subir para "
        "20% e ver só o que foge do reajuste.",
        "ajuste_user": "quem foi admitido no meio do mês anterior aparece como variação "
        "gigante, porque recebeu proporcional. dá pra tirar esses?",
        "ajuste_ia": "Dá. Quem tem admissão dentro do mês de comparação agora vai para a "
        "aba Admitidos e sai da lista de variação, porque a comparação não faria sentido "
        "mesmo. Você continua vendo a pessoa, só não no meio dos alertas.",
        "patch": None,
        "fecho_user": "perfeito, era isso. deixa no ar",
        "fecho_ia": "Publicado em **/app/confere-folha**. Roda em uns 4 segundos com "
        "300 linhas, dá pra usar durante a conferência mesmo.",
    },
    "extrato-dominio": {
        "pedido": "preciso pegar o extrato do banco em csv e transformar no arquivo de "
        "importação do domínio, já com a conta contábil de cada lançamento. hoje é tudo "
        "na mão e é o que mais toma tempo do fechamento",
        "contexto": "Esse é o tipo de coisa que compensa muito automatizar. Mas o layout "
        "do Domínio é exigente, então preciso descer no detalhe com você.",
        "perguntas": [
            {
                "id": "classificacao",
                "label": "Como decido a conta contábil de cada lançamento?",
                "options": [
                    "Por palavra-chave no histórico (tarifa, pix, darf...)",
                    "Por uma planilha De/Para que eu mantenho",
                    "Deixo em branco e classifico depois",
                ],
                "recommended": "Por palavra-chave no histórico (tarifa, pix, darf...)",
                "resposta": "Por palavra-chave no histórico (tarifa, pix, darf...)",
            },
            {
                "id": "conta_banco",
                "label": "A conta do banco é sempre a mesma?",
                "options": [
                    "Não, eu informo na hora de rodar",
                    "Sim, é sempre a 1101",
                ],
                "recommended": "Não, eu informo na hora de rodar",
                "resposta": "Não, eu informo na hora de rodar",
            },
            {
                "id": "sem_regra",
                "label": "E o lançamento que nenhuma regra pegar?",
                "options": [
                    "Joga numa conta transitória e me mostra quantos foram",
                    "Deixa a coluna vazia",
                ],
                "recommended": "Joga numa conta transitória e me mostra quantos foram",
                "resposta": "Joga numa conta transitória e me mostra quantos foram",
            },
            {
                "id": "sinal",
                "label": "Crédito e débito: confirmo que valor positivo é entrada no banco?",
                "options": ["Sim, positivo é entrada", "Não, é o contrário"],
                "recommended": "Sim, positivo é entrada",
                "resposta": "Sim, positivo é entrada",
            },
        ],
        "montagem": "Li o extrato de exemplo: 487 lançamentos, de 01/06 a 30/06. Apliquei "
        "as regras por palavra-chave e classifiquei 453 (93%); 34 caíram na conta "
        "transitória 9999 e aparecem no resumo para você decidir.\n\n"
        "A saída é o txt no layout do Domínio, com data, conta de débito, conta de "
        "crédito, valor com vírgula decimal e o histórico truncado em 200 caracteres. "
        "Entrada no banco debita o banco e credita a contrapartida; saída inverte.",
        "ajuste_user": "o domínio reclamou do arquivo. acho que é o encoding, os "
        "acentos vieram tudo estranho",
        "ajuste_ia": "É isso mesmo. O Domínio espera latin-1, não UTF-8. Troquei a "
        "gravação e coloquei um substituto para qualquer caractere fora da tabela, assim "
        "o arquivo nunca quebra no meio da importação por causa de um símbolo solto.",
        "patch": "with open(out, \"w\", encoding=\"latin-1\", errors=\"replace\") as f:",
        "fecho_user": "importou limpo agora. valeu",
        "fecho_ia": "Ótimo. Está em **/app/extrato-dominio**. Se aparecerem muitos "
        "lançamentos na 9999 num mês, me chama que a gente acrescenta as regras novas.",
    },
    "contratos-vencendo": {
        "pedido": "queria uma rotina que olhasse a base de contratos e me dissesse o que "
        "vence nos próximos dias, pra eu avisar o cliente antes de virar renovação "
        "automática",
        "contexto": "Combinado. Duas perguntas rápidas e uma sobre o aviso.",
        "perguntas": [
            {
                "id": "janela",
                "label": "Quantos dias de antecedência você quer olhar?",
                "options": ["30 dias", "60 dias", "Eu escolho na hora"],
                "recommended": "Eu escolho na hora",
                "resposta": "Eu escolho na hora",
            },
            {
                "id": "vencidos",
                "label": "E os que já venceram, entram?",
                "options": [
                    "Sim, numa aba separada",
                    "Não, só os que estão por vencer",
                ],
                "recommended": "Sim, numa aba separada",
                "resposta": "Sim, numa aba separada",
            },
            {
                "id": "aviso",
                "label": "Quer que eu já monte o texto do aviso para você copiar?",
                "options": [
                    "Sim, um texto pronto com a lista",
                    "Não, só a planilha basta",
                ],
                "recommended": "Sim, um texto pronto com a lista",
                "resposta": "Sim, um texto pronto com a lista",
            },
        ],
        "montagem": "Rodei sobre a base que você mandou: 9 contratos vencem nos próximos "
        "30 dias e 2 já estavam vencidos (passaram batido). A planilha sai com as duas "
        "abas, ordenada por quem vence primeiro, e junto vem o texto do aviso pronto, uma "
        "linha por contrato, com cliente, objeto e dias restantes.\n\n"
        "Deixei o envio de e-mail de fora de propósito: enquanto o texto é copiado por "
        "você, ninguém dispara nada para o cliente por engano.",
        "ajuste_user": "os contratos com renovação automática eu não preciso avisar, "
        "só os que exigem assinatura nova",
        "ajuste_ia": "Ajustado: agora o script olha a coluna Renovação e separa os "
        "automáticos numa aba própria, fora do aviso. Se a coluna não existir na planilha, "
        "ele avisa em português em vez de quebrar.",
        "patch": None,
        "fecho_user": "ótimo, deixa no ar que eu rodo toda sexta",
        "fecho_ia": "Está em **/app/contratos-vencendo**. Quando quiser, dá para agendar "
        "para rodar sozinho toda sexta de manhã e te mandar o resultado.",
    },
    "amostragem-auditoria": {
        "pedido": "na auditoria eu preciso tirar uma amostra do razão pra testar. hoje eu "
        "pego os maiores valores e uns aleatórios no olho, mas não consigo justificar a "
        "cobertura pro papel de trabalho",
        "contexto": "Esse último ponto é o que importa: a amostra tem que ser defensável. "
        "Três perguntas.",
        "perguntas": [
            {
                "id": "criterio",
                "label": "Como você quer compor a amostra?",
                "options": [
                    "Metade maiores valores, metade aleatória",
                    "Só os maiores valores",
                    "Totalmente aleatória",
                ],
                "recommended": "Metade maiores valores, metade aleatória",
                "resposta": "Metade maiores valores, metade aleatória",
            },
            {
                "id": "tamanho",
                "label": "Tamanho da amostra?",
                "options": ["25 itens", "50 itens", "Eu informo a cada trabalho"],
                "recommended": "Eu informo a cada trabalho",
                "resposta": "Eu informo a cada trabalho",
            },
            {
                "id": "cobertura",
                "label": "Precisa registrar quanto do valor total a amostra cobre?",
                "options": ["Sim, é o que vai no papel de trabalho", "Não precisa"],
                "recommended": "Sim, é o que vai no papel de trabalho",
                "resposta": "Sim, é o que vai no papel de trabalho",
            },
        ],
        "montagem": "Testei com o razão que você anexou: 8.104 lançamentos, R$ 12.908.431,77 "
        "no total. Com amostra de 25, peguei os 12 maiores valores mais 13 aleatórios e a "
        "cobertura ficou em 61,4% do valor da população.\n\n"
        "Cada linha sai marcada com o critério pelo qual entrou (valor ou aleatória), que "
        "é exatamente o que o revisor pede para ver.",
        "ajuste_user": "toda vez que eu rodo dá uma amostra aleatória diferente. pro papel "
        "de trabalho eu preciso conseguir repetir a mesma seleção",
        "ajuste_ia": "Ponto justo, e é uma exigência de rastreabilidade mesmo. Coloquei "
        "uma semente: o número que gerou a amostra vai no resumo e você pode informá-lo "
        "de novo para reproduzir exatamente a mesma seleção meses depois.",
        "patch": "semente = int(data.get(\"semente\") or random.randint(1, 9999))\n"
        "aleatoria = resto.sample(n=n_aleatorio, random_state=semente)",
        "fecho_user": "agora sim, é isso que a revisão pede. publica",
        "fecho_ia": "No ar em **/app/amostragem-auditoria**. A semente aparece no resumo "
        "de cada execução, então dá para reproduzir qualquer amostra antiga.",
    },
    "horas-cliente": {
        "pedido": "preciso fechar as horas do mês por cliente e por pessoa pra faturar. "
        "hoje é um export do sistema de apontamento e muita tabela dinâmica no excel",
        "contexto": "Dá para tirar a tabela dinâmica do caminho. Duas perguntas.",
        "perguntas": [
            {
                "id": "recorte",
                "label": "Você precisa do total por cliente, por pessoa, ou os dois?",
                "options": ["Os dois, em abas separadas", "Só por cliente"],
                "recommended": "Os dois, em abas separadas",
                "resposta": "Os dois, em abas separadas",
            },
            {
                "id": "valor",
                "label": "A planilha tem valor/hora para eu já calcular o faturável?",
                "options": [
                    "Tem, pode calcular",
                    "Não tem, só as horas",
                ],
                "recommended": "Tem, pode calcular",
                "resposta": "Tem, pode calcular",
            },
        ],
        "montagem": "Rodei com o export de julho: 1.240 apontamentos, 37 clientes, "
        "2.918 horas no total. Saem duas abas, uma por cliente (com o faturável somado) "
        "e outra por colaborador dentro de cada cliente.\n\n"
        "Se a coluna de valor/hora não vier num mês, o script simplesmente entrega as "
        "horas sem o faturável, em vez de dar erro.",
        "ajuste_user": "tem apontamento com horas em branco e o total fica errado",
        "ajuste_ia": "Tratei: horas vazias ou com texto viram zero e o resumo passa a "
        "mostrar quantos apontamentos vieram assim. Assim você vê o problema na origem "
        "em vez de descobrir pelo total torto.",
        "patch": None,
        "fecho_user": "boa. antes de publicar, queria que isso rodasse sozinho no "
        "fechamento",
        "fecho_ia": "Consigo agendar. Só preciso saber duas coisas para acertar o "
        "gatilho:",
        # entrevista ainda ABERTA: a última fala do assistente traz perguntas, então a
        # interface mostra o painel de entrevista ao vivo neste projeto.
        "entrevista_aberta": [
            {
                "id": "quando",
                "label": "Em que dia do mês devo rodar o fechamento das horas?",
                "options": ["Todo dia 1º", "Todo dia 5", "Última sexta do mês"],
                "recommended": "Todo dia 5",
            },
            {
                "id": "destino",
                "label": "E o que faço com o resultado quando rodar sozinho?",
                "options": [
                    "Só deixar disponível para download",
                    "Deixar disponível e me avisar por e-mail",
                ],
                "recommended": "Só deixar disponível para download",
            },
        ],
    },
    "faturamento-mensal": {
        "pedido": "quero consolidar as notas emitidas por serviço, por cliente e por "
        "competência, com a variação de um mês pro outro. é o número que a diretoria "
        "pede toda reunião",
        "contexto": "Certo. Como isso vai para a diretoria, o corte importa. Duas perguntas.",
        "perguntas": [
            {
                "id": "competencia",
                "label": "A competência é pela data de emissão da nota?",
                "options": [
                    "Sim, pela emissão",
                    "Não, pelo mês de referência do serviço",
                ],
                "recommended": "Sim, pela emissão",
                "resposta": "Sim, pela emissão",
            },
            {
                "id": "cortes",
                "label": "Quais visões você quer no arquivo?",
                "options": [
                    "Mensal, por serviço e por cliente",
                    "Só o total mensal",
                ],
                "recommended": "Mensal, por serviço e por cliente",
                "resposta": "Mensal, por serviço e por cliente",
            },
        ],
        "montagem": "Testei com as notas de maio a julho: 421 notas. Saem três abas, "
        "mensal (com a variação percentual mês a mês já calculada), por serviço e por "
        "cliente, essa última ordenada do maior para o menor.\n\n"
        "O ticket médio e o total do período vão no resumo da execução, que é o que "
        "costuma virar slide.",
        "ajuste_user": "na reunião sempre perguntam quem são os 10 maiores clientes do "
        "trimestre. dá pra ter isso separado?",
        "ajuste_ia": "Dá, e é uma aba a mais. Propus o ajuste aqui embaixo: uma aba "
        "**Top 10** com os maiores clientes do período carregado e o quanto cada um "
        "representa do total. Aprova aí que eu aplico.",
        "patch": None,
        "fecho_user": None,
        "fecho_ia": None,
        "pendente": {
            "kind": "edit_file",
            "title": "Adicionar aba Top 10 clientes do período",
            "resumo": "top10 = por_cliente.groupby(\"Cliente\")[\"Valor\"].sum()"
            ".nlargest(10).reset_index()",
        },
    },
}
