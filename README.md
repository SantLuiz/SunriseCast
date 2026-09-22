# SunriseCast

> **Atualização 2.0.0 (21/09/2026):** sincronização em worker, espera do Spotify persistida, limpeza por 14 dias sem avanço e Histórico com restauração múltipla. Consulte [o contexto atualizado](PROJECT_CONTEXT.md), [o guia de atualização e reversão](UPDATE_GUIDE.md) e [a validação](VALIDATION.md). O [overhaul visual](UI_OVERHAUL_PLAN.md) permanece separado. As instruções antigas abaixo descrevem a versão inicial; para esta entrega, use Python 3.12 em `.venv`, `requirements-lock.txt` e `build_windows.ps1` (saída em `release/2.0.0`).

<p align="right">
  <img src="https://img.shields.io/badge/Python-3.10+-blue" />
  <img src="https://img.shields.io/badge/Spotify-API-1DB954" />
  <img src="https://img.shields.io/badge/Spotipy-2.24-yellow" />
  <img src="https://img.shields.io/badge/Status-Em%20desenvolvimento-orange" />
</p>

O **SunriseCast** é um projeto de automação em Python criado para manter uma playlist do Spotify sempre organizada e atualizada com episódios recentes dos seus podcasts favoritos.

A proposta do projeto é eliminar a necessidade de gerenciar manualmente episódios de podcasts, automatizando todo o processo de atualização da playlist de forma inteligente e contínua.

O sistema funciona integrando-se à API do Spotify, analisando tanto o conteúdo da playlist quanto os podcasts configurados pelo usuário, garantindo que apenas episódios relevantes e ainda não consumidos estejam disponíveis.

## Funcionalidades

O SunriseCast foi projetado com base nos seguintes requisitos principais:

- **Limpeza automática da playlist**  
  Verifica a playlist configurada e remove automaticamente os episódios que já foram finalizados.

- **Monitoramento de podcasts favoritos**  
  Percorre a lista de podcasts definida no arquivo `podcasts.json` e identifica todos os episódios:
  - Mais recentes que um intervalo de dias configurável
  - Que ainda não foram finalizados
  - Considerando múltiplos episódios lançados dentro do intervalo

- **Adição inteligente de episódios**  
  Adiciona novos episódios à playlist respeitando:
  - A ordem de prioridade definida no `podcasts.json`
  - A posição correta entre episódios já existentes
  - A preservação dos episódios ainda não escutados

- **Organização baseada em prioridade**  
  Mantém a playlist organizada de acordo com a precedência dos podcasts, garantindo uma experiência consistente de consumo.

- **Interface simples e funcional**
  O sistema conta com uma interface leve contendo:
  - Botão para executar manualmente a sincronização
  - Opção para ativar/desativar sincronização automática
  - Configuração de horários e frequência diária de execução
  - Definição do intervalo de dias para busca de episódios
  - Aba para gerenciar podcasts (adicionar, remover e definir prioridade)

- **Execução em segundo plano**
  O programa é executado continuamente em background, realizando sincronizações automáticas no horário definido, com acesso à interface através de um ícone na barra de tarefas do Windows (system tray), semelhante a aplicativos como Wi-Fi e Bluetooth.

## Objetivo

O objetivo do SunriseCast é transformar a forma como você consome podcasts, automatizando a curadoria e organização dos episódios, garantindo que sua playlist esteja sempre atualizada, relevante e pronta para uso.

## Autenticação e configuração no Spotify for Developers

Para que o SunriseCast consiga acessar sua conta, ler informações dos podcasts e modificar uma playlist, é necessário configurar uma aplicação no **Spotify for Developers**. Isso acontece porque o Spotify utiliza **OAuth 2.0** para autorizar aplicações a acessarem recursos da conta do usuário, como playlists e biblioteca.

A criação dessa aplicação deve ser feita no **Developer Dashboard** do Spotify. Após criar o app e selecionar o uso da **Web API**, você terá acesso ao **Client ID** e ao **Client Secret**, que serão usados pelo projeto durante a autenticação.

Também é obrigatório cadastrar uma **Redirect URI** nas configurações do app. Essa URI precisa ser exatamente igual à utilizada no código e no arquivo de variáveis de ambiente, pois o Spotify redireciona o usuário para esse endereço após a autorização.

### Links úteis

- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/)
- [Getting Started - Spotify Web API](https://developer.spotify.com/documentation/web-api/tutorials/getting-started)
- [Apps / Developer Dashboard](https://developer.spotify.com/documentation/web-api/concepts/apps)
- [Spotipy Documentation](https://spotipy.readthedocs.io/)

## Arquivos necessários para a autenticação e execução

Como o projeto usa arquivos locais e parte deles não deve ser enviada ao GitHub, alguns arquivos precisam ser criados manualmente no ambiente onde o programa será executado.

### `.env`
Arquivo responsável por armazenar as credenciais e configurações principais do projeto.

Exemplo:

```env
SPOTIPY_CLIENT_ID=seu_client_id
SPOTIPY_CLIENT_SECRET=seu_client_secret
SPOTIPY_REDIRECT_URI=http://localhost:8888/callback
PLAYLIST_ID=id_da_playlist
```

Esse arquivo é essencial porque o Spotipy suporta autenticação a partir dessas variáveis, e o projeto depende delas para iniciar a sessão com a API do Spotify
Quando o projeto for empacotado, e importante que o . env esteja no mesmo diretorio do .exe para o programa funcionar corretamente

### `.spotify_cache`
Arquivo gerado automaticamente após o primeiro login. Ele armazena o token de acesso em cache para evitar que a autenticação precise ser refeita a cada execução. No SunriseCast, isso é controlado pelo SpotifyOAuth com cache_path=".spotify_cache".

### `podcasts.json`

Arquivo responsável por definir **quais podcasts serão monitorados** pelo sistema e **a ordem de prioridade** em que devem aparecer na playlist.

Estrutura:

```json
{
  "shows": [
    {
      "name": "Nome do Podcast",
      "show_id": "spotify_show_id",
      "priority": 6
    }
  ]
}

```

shows: lista de podcasts monitorados
name: nome amigável do podcast (apenas informativo)
show_id: identificador único do podcast no Spotify (obrigatório),
priority: hierarquia deste item em relação aos outros


### `state.json`
Arquivo usado para registrar o estado atual do processamento, permitindo ao sistema controlar episódios já tratados e manter consistência entre execuções.

```json
{
  "processed_episode_ids": [
    "id_do_episodio_1",
    "id_do_episodio_2"
  ]
}

 "last_sync_at": "2000-00-00T00:00:00",
 "last_removed_count": 0,
 "last_playlist_size": 00

```

### `settings.json`
Arquivo usado para registrar prefefências do usuario, alterado pela aplicação

```json
{
  "auto_sync_enabled": false,
  "interval_days": 7,
  "sync_times": [
    "08:00"
  ]
}
```


### **Importante!**
**Arquivos como `.env`, `.spotify_cache`, `state.json` e outros conteúdos locais da pasta data/ não devem ser versionados, pois podem expor credenciais, tokens ou estados internos da aplicação. Por isso, eles devem permanecer ignorados pelo Git.**


## Como executar o projeto

Siga os passos abaixo para configurar e rodar o SunriseCast em seu ambiente local.

### 1. Criar ambiente virtual (venv)

No diretório do projeto, execute:

```bash
python -m venv venv
```
- Windows -> venv\Scripts\activate
- Linux / macOS -> source venv/bin/activate

### 2. Instalar dependências
Com o ambiente virtual ativado, instale as bibliotecas do projeto:

```bash
pip install -r requirements.txt
```
### 3. Configurar arquivos necessários

Antes de rodar, certifique-se de que você criou e configurou:

- .env (credenciais do Spotify)
- podcasts.json (lista de podcasts)
- state.json (pode iniciar vazio)
- settings.json(preferências)

### 4. Executar o projeto

```bash
python run.py
```

### **Observações!**
- Na primeira execução, um navegador será aberto para autenticação no Spotify
- Após o login, o token será salvo automaticamente em .spotify_cache
- O script irá sincronizar a playlist conforme as regras definidas no projeto

## 5. Gerando o executável (.exe) no Windows

Para gerar o executável do SunriseCast, utilize o script PowerShell incluído no projeto.

### Pré-requisitos

- Windows
- Python instalado
- Ambiente virtual (`venv`) criado
- Dependências instaladas:
  pip install -r requirements.txt
- PyInstaller instalado:
  pip install pyinstaller

### Executando o build

Na raiz do projeto, execute:

.build_windows.ps1

Caso o PowerShell bloqueie a execução de scripts, utilize:

Set-ExecutionPolicy -Scope Process Bypass .build_windows.ps1

### Saída

Após a execução, o executável estará disponível em:

dist\SunriseCast\SunriseCast.exe

### Observações

- O script realiza automaticamente:
  - Limpeza de builds anteriores
  - Ativação do ambiente virtual (se existir)
  - Inclusão das pastas `assets` e `data`
  - Uso do arquivo `SunriseCast.spec` para configuração do build

- Sempre teste o executável dentro da pasta `dist` antes de distribuir.

