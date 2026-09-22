# SunriseCast — contexto do projeto

Atualizado em 21/09/2026 durante a implementação da correção 2.0.0. Este documento substitui o diagnóstico preliminar. A verificação usa respostas simuladas; nenhuma sincronização foi executada na conta real nesta entrega.

## Diagnóstico da instalação real

Instalação real observada: `%USERPROFILE%\OneDrive\Documentos\SunriseCast`. O projeto usado para desenvolvimento fica em outra cópia, com dados mais antigos.

Os registros da instalação apontam último sucesso em **18/09/2026**, com **321 episódios**. Execuções posteriores consultaram cada episódio individualmente e repetiram essas consultas ao conferir a ordem. As retentativas do cliente HTTP aguardavam quase 24 horas na própria thread Qt. Em 20/09, uma execução encontrou token expirado após aproximadamente seis horas de espera. A leitura feita em 21/09 confirmou novo bloqueio às 07:09:15, com espera de **84.103 segundos**.

A correção elimina a espera na interface e reduz requisições; não antecipa a liberação da quota do Spotify.

Referências oficiais verificadas:

- [Itens de playlist](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items): páginas de até 50 e `resume_point` com escopo `user-read-playback-position`.
- [Atualização de quota de julho de 2026](https://developer.spotify.com/blog/2026-07-23-web-api-quota-updates): resposta 429 pode informar `QUOTA_EXCEEDED`.

## Ambiente e execução

Python **3.12.13** em `.venv/`, separado do `venv/` antigo e quebrado, que foi preservado. Dependências diretas em `requirements.txt`, testes/build em `requirements-dev.txt`, todas as versões resolvidas em `requirements-lock.txt`. Versões principais: Spotipy 2.26.0, PySide6 6.11.2, pytest 9.1.1, pytest-qt 4.5.0 e PyInstaller 6.22.3.

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-lock.txt
.\.venv\Scripts\python.exe run.py
.\.venv\Scripts\python.exe -m pytest -q
.\build_windows.ps1
```

Entrada oficial: `run.py`. No executável, o diretório de trabalho é fixado na pasta do EXE antes de carregar dados, logs e `.env`. `QLockFile` impede duas instâncias novas na mesma instalação. Fechar a janela mantém a bandeja; **Sair** interrompe cooperativamente o worker e só encerra o processo após a conclusão. A versão antiga não participa desse lock; deve ser fechada antes da atualização.

Credenciais exigidas: `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI`, `PLAYLIST_ID`. Nunca copiar tokens ou valores de credenciais para documentação, logs ou commits. A autorização manual usa retorno HTTP local com porta, parâmetro `state` validado e prazo de 120 segundos. A renovação de token ocorre automaticamente quando possível; tarefas automáticas sinalizam necessidade de login sem abrir um navegador.

## Arquitetura atual

| Componente | Responsabilidade |
| --- | --- |
| `OperationController` | Entrada única para janela, bandeja e agendador; execução exclusiva, sinais Qt, espera e encerramento |
| `OperationWorker` | `QObject` em `QThread`; executa o serviço e persiste resultado, espera ou operação pendente |
| `SpotifyGateway` | Chamadas com cancelamento entre requisições, cache de episódios por operação e tradução de erros |
| `BoundedSpotifyOAuth` | Login manual limitado e renovação com timeouts |
| `PlaylistService` | Leitura paginada, mapeamento `track`/`item`, progresso e ordem desejada |
| `SyncService` | Limpeza, novidades, restauração, journal de alterações e reconciliação |
| `domain/progress.py` | Regras de inatividade e proteção da conclusão após restauração |
| `StateRepository` | Estado v2 validado, migração com backup e escrita atômica |
| `HistoryTab` | Pesquisa local, filtros, seleção múltipla, contador e resultado por episódio |

A interface recebe somente sinais do controlador; o worker nunca acessa widgets. Navegação e pesquisa continuam disponíveis; os botões que gravam configurações são bloqueados enquanto há operação. Não há porcentagens fictícias.

O agendador verifica horários a cada 30 segundos, normalizados como `HH:MM`, e registra o disparo daquele minuto em memória para não repetir falhas imediatamente. O controlador verifica a espera persistida por temporizador de um segundo, sem manter worker dormindo.

## Rede e limites

Sessão `requests` compartilhada pelo cliente e OAuth, com `HTTPAdapter(max_retries=0)`; Spotipy também tem retentativas e backoff internos desabilitados. Timeouts de conexão/leitura: **5/20 segundos**.

Leitura de playlist em páginas de **50**. `fully_played` e `resume_position_ms` vêm da playlist sempre que disponíveis. Apenas campos ausentes motivam consulta individual, com cache limitado à operação. Leituras de confirmação e organização não repetem consultas de progresso. Erros 403/404 de detalhe deixam progresso desconhecido, sem presumir inatividade.

429 preserva `Retry-After` e motivo; `QUOTA_EXCEEDED` tem mensagem própria. O worker persiste o instante permitido e a operação e termina. Sem cabeçalho válido, a espera cresce de 60 segundos até uma hora (60, 120, 240, 480, 960, 1920, 3600). Reiniciar o aplicativo não remove essa espera. A retomada automática exige aplicativo aberto e preferências automáticas habilitadas; recomeça com leitura atual e autenticação válida.

Falhas comuns e cancelamento não criam um loop automático de retentativas. Um login manual posterior pode renovar um token rejeitado por 401. Limites encontrados durante OAuth seguem o mesmo tratamento de quota.

## Limpeza e progresso

Um episódio é encalhado somente após **mais de 14 dias sem avanço observado**. Exatamente 14 dias não remove.

- Aumento da posição renova o prazo.
- Posição igual ou menor não renova. Retrocesso passa a ser a referência para detectar aumentos futuros.
- Publicação não define inatividade. Reorganização não reinicia o prazo.
- Na primeira observação, não iniciados com `added_at` conhecido podem ser removidos se ultrapassarem 14 dias. Parcialmente ouvidos começam a observação naquele instante.
- Datas inválidas/ausentes e progresso desconhecido não fundamentam remoção por inatividade. Quando dados suficientes aparecem depois, começa uma observação nova.
- Finalizado tem precedência sobre encalhado.

Restaurar reinicia a observação. Uma conclusão antiga é ignorada até observar uma reprodução incompleta seguida de conclusão. Sem avanço e com posição conhecida, o episódio volta a ser removido por inatividade após o novo prazo. Se a posição ainda é desconhecida, aguarda dados suficientes.

## Estado v2 e alterações remotas

`data/state.json` mantém IDs processados e estatísticas anteriores e acrescenta:

- `version: 2`;
- `progress[playlist_id][episode_id]`, com posição, último avanço e proteção de conclusão;
- `history`, com ID único por evento, playlist, episódio, motivo, situação, horários e erro individual;
- `pending_mutation`, com intenção do lote antes de alterar o Spotify;
- `pending_operation`, seleção de restauração quando aplicável e indicação de retomada automática;
- `spotify_wait` e `rate_limit_streak`.

Migração cria `state.json.v1-<id>.bak`, preserva campos existentes e não inventa remoções antigas. Um JSON inválido/incompatível gera erro e permanece intacto. Gravações usam temporário no mesmo diretório, flush, fsync e substituição atômica. Podcasts e preferências também usam escrita atômica.

Se o atualizador encontrou espera legada ainda válida no log, grava `data/legacy_spotify_wait.json`; a migração v1 importa essa espera uma única vez. Estados v2 não reaplicam esse arquivo.

Cada lote remoto tem intenção persistida antes da chamada. Adições/remoções são confirmadas por releitura da playlist. Se houver resposta ambígua ou interrupção antes da confirmação local, a próxima execução confere presença/ausência antes de planejar o trabalho restante. Não repete cegamente uma requisição antiga. Itens a conferir não aparecem como removidos/restaurados com sucesso.

Removidos continuam nos IDs processados, impedindo reinserção automática. O histórico permanece após restauração e futuras remoções criam eventos distintos. Remoções não confirmadas não atualizam o último sucesso de sincronização.

## Ordenação e novidades

Mantidas as regras existentes de prioridade de podcast, data e nome decrescentes dentro do podcast. Podcasts fora do cadastro vêm ao final, por ID. O intervalo configurado ainda filtra somente as novidades, não a idade de itens existentes.

A ordenação usa reposicionamento de blocos contíguos, sem substituir toda a playlist. Isso preserva músicas, itens não mapeados e ocorrências repetidas existentes. Um item indisponível sem URI impede a operação com mensagem explícita, pois não há como conferir sua ordem com segurança.

Adições e remoções usam até 100 itens por lote. Restauração ignora recência e IDs processados, evita duplicatas e respeita a ordem por podcast. Se o Spotify recusar um lote com HTTP 400/403/404, a operação confere o estado remoto e isola os resultados por episódio. Erros de rede, quota ou autenticação interrompem o worker, preservando o journal para recuperação.

Não há transação distribuída com o Spotify. Edições externas concorrentes ainda podem alterar a playlist durante o fluxo; divergências encontradas na conferência final são informadas e exigem nova sincronização. Não se promete atribuir exatamente o horário de uma alteração remota que só foi confirmada após interrupção.

## Histórico e interface

A aba Histórico mostra episódio, podcast, remoção, motivo e situação. Pesquisa e filtros são locais; ordenação pela remoção mais recente. Seleção com Ctrl/Shift e **Restaurar selecionados (N)**. Erros individuais ficam no tooltip da situação e falhas continuam disponíveis para nova tentativa. A seleção de podcast durante edição cancela a edição anterior, evitando salvar dados no registro errado.

A interface mantém a estrutura atual; o tema escuro e a navegação lateral futura estão em `UI_OVERHAUL_PLAN.md`. Não tratar esse overhaul como implementado.

## Build, validação e atualização

`SunriseCast.spec` deixou de ser ignorado e inclui apenas recursos de `assets/`, sem `data/`. `build_windows.ps1` usa `.venv`, verifica Python 3.12, executa testes por padrão e gera `release/2.0.0/SunriseCast/`. Não apaga o ambiente antigo nem as saídas anteriores de `dist/`. O pacote é verificado para ausência de arquivos pessoais.

O modo `run.py --smoke-test artifacts/ui-source` e o equivalente no EXE constroem a interface com dados fictícios, sem carregar OAuth nem `.env`, e exportam cinco capturas e um resultado JSON. As telas de histórico foram inspecionadas em 1000 × 650 e 800 × 500, incluindo estado de espera. O plugin Qt offscreen recebe uma fonte nativa do Windows apenas para essa renderização.

Cobertura de testes: 321 itens sem consultas individuais, fallback e cache, regras de progresso, migração/backup/estado inválido, escrita atômica, 429 de 86 mil segundos, reinício, retomada automática, OAuth expirado, login limitado, UI responsiva, exclusão de operações concorrentes, encerramento cooperativo, filtros e seleção, restauração em lotes e falhas parciais, interrupções entre remoto e gravação local, preservação de músicas e regras existentes. O atualizador é testado contra uma instalação fictícia em preparar/aplicar/reverter, incluindo integridade dos dados.

`update_installation.ps1` permite preparar backup completo com hashes, aplicar a troca somente dos binários e reverter com novo backup do estado atual. Não encerra processos à força. `UPDATE_GUIDE.md` contém os comandos. Backups pessoais ficam fora do pacote distribuível e nunca devem ser enviados ao Git.

### Bloqueio do executável corrigido em 21/09/2026

O executável falhava ao importar QtCore/QtWidgets com “DLL load failed: Não foi possível encontrar o procedimento especificado”. A análise do PyInstaller capturava dependências pelo PATH herdado do ambiente do Codex: incluía `icuuc.dll` do Poppler e `ucrtbase.dll` do libheif. A ICU do Poppler exporta `ucnv_open_78`, enquanto o Qt importa `ucnv_open`, fornecida pela ICU do Windows. Portanto, adicionar diretórios de DLL em `run.py` não resolvia a dependência incompatível já empacotada.

`SunriseCast.spec` agora restringe o PATH de descoberta ao Python utilizado e aos diretórios do Windows antes de executar Analysis. O build limpo foi repetido com sucesso; o manifesto não contém dependências do runtime do Codex e o pacote não contém a ICU do Poppler.

Validação específica: o EXE reconstruído executou `--smoke-test` com código de saída zero, quatro registros fictícios de histórico e cinco capturas. Evidência em `artifacts/ui-dll-fix-20260921-213004/smoke-result.json` (`ok: true`, sem rede nem dados pessoais). Depois da retomada, a suíte completa passou novamente e o smoke padrão foi refeito em `artifacts/ui-executable/smoke-result.json`.

Durante a retomada, o teste do atualizador expôs uma dependência indevida do ambiente real: qualquer processo `SunriseCast.exe` aberto bloqueava o teste com instalação fictícia. `update_installation.ps1` agora confere apenas processos executados dentro da instalação indicada por `-InstallPath`, preservando a proteção da atualização real sem interferir em testes isolados.

`VALIDATION.md` e o ZIP distribuível foram gerados após essa validação. A instalação real não foi alterada.

Tentativas de aplicar a atualização na instalação real criaram backups verificados em `%LOCALAPPDATA%\SunriseCast\backups\`. Uma tentativa com `Move-Item` deixou `_internal` parcialmente movido; os arquivos faltantes foram restaurados do snapshot e a instalação voltou a conferir com o backup (`missing: 0`, `different: 0`). O atualizador foi ajustado para usar `File.Move`/`Directory.Move`, evitando movimentação recursiva parcial de diretórios.

A aplicação real ainda não foi concluída porque o processo do Codex executa sob permissões que aparecem na ACL como `CodexSandboxUsers` com `ReadAndExecute` nos binários antigos. O usuário local tem `FullControl`, mas o comando executado pelo Codex recebe “Acesso negado” ao renomear `%USERPROFILE%\OneDrive\Documentos\SunriseCast\_internal`. Duas pastas temporárias `.sunrisecast-*` foram preservadas na instalação real para inspeção/recuperação; a limpeza recursiva foi bloqueada pela revisão automática por conter árvores de binários de tentativas parciais.

## Limitações preservadas

- Sem chamadas reais ao Spotify na verificação; quota e disponibilidade externa não são simuláveis integralmente.
- Sem recuperação de horários agendados perdidos com o aplicativo fechado/suspenso; a retomada persistida cobre bloqueios de quota.
- Sem serviço do Windows nem mecanismo de despertar o computador.
- O novo executável não é assinado digitalmente.
- A busca de novidades conserva o corte antigo por data/hora; publicação com precisão menor que dia continua ignorada.
- Preferências antigas inválidas ainda usam a política anterior; a proteção estrita contra perda silenciosa foi aplicada ao estado/histórico.
