# Validacao da entrega SunriseCast 2.0.0

Data: 21/09/2026

## Resultado

A entrega foi validada com dados simulados, sem chamadas reais ao Spotify e sem carregar dados pessoais da instalacao real.

## Comandos executados

```powershell
.\build_windows.ps1
```

Resultado: `48 passed` e build limpo gerado em `release\2.0.0\SunriseCast\SunriseCast.exe`.

```powershell
release\2.0.0\SunriseCast\SunriseCast.exe --smoke-test artifacts\ui-executable
```

Resultado:

```json
{
  "ok": true,
  "network_used": false,
  "personal_data_loaded": false,
  "history_rows": 4,
  "screenshots": 5
}
```

## Cobertura verificada

- Leitura de playlist com progresso vindo dos itens, fallback apenas quando necessario e cache por operacao.
- Tratamento de `429`, persistencia de espera, retomada automatica e login manual limitado.
- Execucao em worker Qt, operacao unica, cancelamento cooperativo e janela responsiva.
- Regra de 14 dias sem avanco, primeira limpeza, progresso desconhecido, avanco e retrocesso.
- Historico de remocoes, filtros, selecao multipla, restauracao em lote e falhas parciais.
- Estado local versionado, migracao com backup, escrita atomica e recuperacao de operacoes ambiguas.
- Atualizador com preparar, aplicar e reverter preservando `.env`, cache, dados, logs e inicializacao.
- Empacotamento sem `.env`, `.spotify_cache`, dados pessoais, logs ou runtime nativo indevido do Codex.

## Artefatos

- Smoke test do executavel: `artifacts\ui-executable\smoke-result.json`
- Capturas de interface ficticia: `artifacts\ui-executable\*.png`
- Executavel validado: `release\2.0.0\SunriseCast\SunriseCast.exe`
- Informacoes de build: `release\2.0.0\BUILD_INFO.json`
- Pacote distribuivel: `release\SunriseCast-2.0.0-windows-x64.zip`

## Instalacao real

Foram criados backups verificados da instalacao real antes das tentativas de aplicacao. A troca dos binarios em `%USERPROFILE%\OneDrive\Documentos\SunriseCast` nao foi concluida pelo Codex porque o ambiente de execucao recebeu acesso negado ao renomear `_internal`. A instalacao visivel foi conferida contra o snapshot antigo apos a recuperacao (`missing: 0`, `different: 0`) e permanece nos binarios antigos.

O pacote distribuivel e o script de atualizacao estao prontos. Para aplicar fora do sandbox do Codex, use `update_installation.ps1 -Mode Apply` em uma sessao normal do usuario local, com o aplicativo fechado.

## Limites

A validacao nao chama a API real do Spotify. A correcao reduz chamadas e elimina esperas bloqueantes na interface, mas continua respeitando qualquer quota bloqueada pelo Spotify ate o horario permitido pela propria API.
