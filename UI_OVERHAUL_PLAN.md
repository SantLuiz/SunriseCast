# SunriseCast — plano do overhaul visual

Este plano é uma entrega separada. A correção de sincronização e a aba Histórico estão implementadas na interface atual; o tema e a reorganização completa abaixo ficam para uma próxima entrega.

## Direção visual

Manter PySide6, o nome, o ícone e a identidade SunriseCast. Todos os textos em português. Tema escuro: fundo `#121212`, navegação `#0B0B0B`, superfícies `#1E1E1E`, texto `#F5F5F5` e destaque âmbar `#FFB454`. Usar contraste legível, foco de teclado visível e ícones acompanhados de texto.

Janela inicial de 1040 × 720, mínimo de 800 × 600. Preservar geometria, aba selecionada, larguras de colunas e preferências visuais com `QSettings`.

## Estrutura

Navegação lateral com **Podcasts**, **Histórico**, **Atividade** e **Preferências**. Cabeçalho com estado da operação e botão Sincronizar agora. Rodapé com último sucesso confirmado e próximo horário; se houver bloqueio do Spotify, mostrar a data e hora permitidas e se a retomada automática está habilitada.

- **Podcasts:** lista ordenada por prioridade, com inclusão e edição em diálogos separados. Um diálogo edita um ID estável; trocar a seleção da lista não muda o registro em edição. Ações de reordenação acessíveis pelo teclado.
- **Histórico:** aproveitar o repositório e o fluxo de restauração atuais. Pesquisa, filtros, seleção múltipla, contador e resultados individuais. Distinguir removido, restaurado, falha e resultado ainda a conferir. Preservar eventos anteriores quando um episódio for removido novamente.
- **Atividade:** etapas, contagens conhecidas, resultados, espera pelo Spotify e detalhes de erros. Não mostrar percentuais sem total conhecido. Permitir copiar detalhes sem tokens ou credenciais.
- **Preferências:** horários com `QTimeEdit`, inclusão e remoção de horários e explicação da diferença entre janela de novidades e prazo de 14 dias sem avanço.

## Integração

Janela e bandeja consomem o mesmo `OperationController`. A apresentação não gera chamadas adicionais ao Spotify. Durante operações, manter navegação e pesquisa disponíveis; impedir novos disparos e gravações de configurações. Esperas longas liberam o worker e continuam visíveis. O fechamento pela bandeja usa interrupção cooperativa.

## Critérios de aceite futuros

Validar 800 × 600 e 1040 × 720, escala do Windows em 100%, 125% e 150%, navegação por teclado, nomes longos, histórico vazio e extenso, seleção múltipla, falhas parciais, autenticação necessária, quota excedida e restauração interrompida. Confirmar que troca de seleção nunca altera o podcast errado e que preferências visuais sobrevivem ao reinício.
