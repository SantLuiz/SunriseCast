# Atualização para SunriseCast 2.0.0

O pacote contém `SunriseCast/SunriseCast.exe`, `_internal`, o atualizador e este guia. Não contém credenciais, podcasts, preferências ou histórico pessoal. Mantenha `_internal` junto do executável.

## Preparar e aplicar

Feche a versão antiga pelo menu **Sair** na bandeja. Se ela ainda estiver presa na espera antiga, aguarde o encerramento antes de substituir arquivos. O atualizador recusa atualização enquanto houver processo SunriseCast ativo.

Em PowerShell, na pasta do pacote:

```powershell
.\update_installation.ps1 -Mode Prepare -InstallPath "$env:USERPROFILE\OneDrive\Documentos\SunriseCast"
.\update_installation.ps1 -Mode Apply -InstallPath "$env:USERPROFILE\OneDrive\Documentos\SunriseCast"
```

`Prepare` cria e verifica um backup completo, sem alterar a instalação. `Apply` cria outro backup atualizado e troca somente o executável e `_internal`. Preserva `.env`, `.spotify_cache`, `data/`, logs e `iniciar_oculto.vbs`; valida seus hashes. O local padrão dos backups é `%LOCALAPPDATA%\SunriseCast\backups`. É possível escolher outra pasta com `-BackupRoot`.

A espera ainda válida encontrada no log da versão antiga é levada em um arquivo auxiliar para a migração, evitando uma tentativa precoce na primeira abertura. Os arquivos de estado existentes só são migrados pelo aplicativo, com backup próprio. A interface mostra falhas de leitura de estado, em vez de descartá-lo.

Abra o SunriseCast pelo atalho/script habitual após a atualização. A primeira sincronização manual pode pedir autorização pelo navegador, com até 120 segundos para concluir. O agendamento não abre um login oculto. Não houve sincronização com a conta real durante a validação desta versão.

## Reversão

Para voltar integralmente ao momento de um backup, feche o aplicativo e execute:

```powershell
.\update_installation.ps1 -Mode Rollback -InstallPath "$env:USERPROFILE\OneDrive\Documentos\SunriseCast" -BackupPath 'CAMINHO_DO_BACKUP'
```

A reversão restaura também os dados daquele momento. Antes disso, faz outro backup completo do estado atual. Não misture a versão antiga com o estado v2: ela não conhece o histórico novo e pode sobrescrevê-lo.

## Comportamento novo

- A janela e a bandeja continuam utilizáveis durante sincronizações e restaurações.
- Finalizados são removidos; episódios sem avanço observado por **mais de 14 dias** também podem ser removidos. Na primeira observação, apenas não iniciados com data conhecida usam a idade de inclusão. Parcialmente ouvidos ganham 14 dias de observação.
- Histórico mantém cada evento. Restauração múltipla evita duplicatas, reinicia o prazo e permite repetir falhas individuais.
- Limites do Spotify são respeitados até a data permitida. A retomada acontece com o aplicativo aberto e o automático habilitado.
- Uma operação interrompida é conferida com a playlist antes de continuar. Resultados pendentes não são exibidos como concluídos.

O overhaul visual completo está documentado em `UI_OVERHAUL_PLAN.md`, separado desta correção.
