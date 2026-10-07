# Monitor de disponibilidade de sites
[![CI](https://github.com/Mateusmfmd/monitor-disponibilidade-sites/actions/workflows/ci.yml/badge.svg)](https://github.com/Mateusmfmd/monitor-disponibilidade-sites/actions/workflows/ci.yml)

Monitor Python pequeno e autocontido para verificar URLs, guardar o histórico em SQLite e emitir alertas opcionais por e-mail ou Telegram.

> **Privacidade e segurança:** por padrão, o programa faz somente as verificações solicitadas e grava localmente. Ele **não envia e-mail nem acessa o Telegram** quando esses canais não estão configurados. O modo `--simulate` não acessa a rede e também não dispara alertas.

## Requisitos

- Python 3.10 ou superior
- Nenhuma dependência de runtime além da biblioteca padrão

## Instalação

Na raiz do projeto:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

O comando instalado é `monitor-disponibilidade`; também é possível usar `python -m monitor_disponibilidade`.

## Uso rápido

```bash
# URL única (o banco padrão é monitor.db)
monitor-disponibilidade check --url https://example.com

# Várias URLs, timeout de 3 s e duas tentativas adicionais
monitor-disponibilidade --url https://example.com --url https://example.org \
  --timeout 3 --retries 2 --database dados/monitor.db

# Ver o histórico salvo
monitor-disponibilidade history --database dados/monitor.db --limit 20
monitor-disponibilidade history --database dados/monitor.db --url https://example.com --json

# Execução determinística sem nenhum acesso de rede
monitor-disponibilidade check --url https://nao-sera-acessada.invalid --simulate --json
```

O código de saída de `check` é `0` quando todas as URLs estão disponíveis, `1` quando pelo menos uma está indisponível e `2` para erro de configuração/execução. A faixa HTTP `200`–`399` é considerada disponível. `--retries N` significa **N tentativas adicionais**, portanto são feitas até `N + 1` tentativas.

## Configuração JSON

Passe `--config caminho.json` (ou defina `MONITOR_CONFIG`). Exemplo:

```json
{
  "urls": [
    {"name": "site principal", "url": "https://example.com"},
    "https://example.org/health"
  ],
  "timeout": 5,
  "retries": 2,
  "database": "dados/monitor.db",
  "notifications": {
    "email": {
      "enabled": true,
      "host": "smtp.example.com",
      "port": 587,
      "username": "monitor@example.com",
      "password": "use-variavel-de-ambiente",
      "sender": "monitor@example.com",
      "recipients": ["oncall@example.com"],
      "starttls": true
    },
    "telegram": {
      "enabled": true,
      "bot_token": "use-variavel-de-ambiente",
      "chat_id": "123456789"
    }
  }
}
```

Para não deixar segredos no arquivo, é recomendado manter a estrutura no JSON e fornecer `MONITOR_EMAIL_PASSWORD` e `MONITOR_TELEGRAM_BOT_TOKEN` no ambiente. Um canal só é considerado configurado quando está habilitado e possui todos os campos mínimos (SMTP: host, remetente e destinatário; Telegram: token e chat ID).

Alertas são enviados somente para um resultado **DOWN**, depois que todas as tentativas terminaram. Uma execução em modo simulação nunca envia alertas.

## Variáveis de ambiente

As variáveis abaixo substituem os valores equivalentes do JSON; argumentos de CLI têm precedência máxima:

| Variável | Descrição |
| --- | --- |
| `MONITOR_CONFIG` | Caminho do JSON |
| `MONITOR_URLS` | URLs separadas por vírgulas |
| `MONITOR_TIMEOUT` | Timeout em segundos |
| `MONITOR_RETRIES` | Tentativas adicionais |
| `MONITOR_DATABASE` ou `MONITOR_DB` | Caminho do SQLite |
| `MONITOR_SIMULATE` | `true`/`false` |
| `MONITOR_EMAIL_ENABLED` | Habilita/desabilita e-mail |
| `MONITOR_EMAIL_HOST`, `MONITOR_EMAIL_PORT` | Servidor e porta SMTP |
| `MONITOR_EMAIL_USERNAME`, `MONITOR_EMAIL_PASSWORD` | Credenciais SMTP |
| `MONITOR_EMAIL_FROM`, `MONITOR_EMAIL_TO` | Remetente e destinatários (vírgulas) |
| `MONITOR_EMAIL_STARTTLS` | `true`/`false` |
| `MONITOR_TELEGRAM_ENABLED` | Habilita/desabilita Telegram |
| `MONITOR_TELEGRAM_BOT_TOKEN`, `MONITOR_TELEGRAM_CHAT_ID` | Credenciais do Bot API |

Sem essas configurações, não há tentativa de conexão com SMTP ou Telegram.

## SQLite

A tabela `checks` guarda URL, nome, instante UTC, disponibilidade, status HTTP, tempo de resposta, número de tentativas e erro. O índice por URL e data permite consultas rápidas pelo subcomando `history`. O banco e seus diretórios-pai precisam ser acessíveis pelo usuário que executa o monitor.

## Desenvolvimento e testes

Os testes usam exclusivamente um `ThreadingHTTPServer` em `127.0.0.1` criado pelo próprio teste. Não há chamadas a sites, SMTP ou Telegram externos:

```bash
python -m pytest
```

A validação contínua está em [`.github/workflows/ci.yml`](.github/workflows/ci.yml), com Python 3.10–3.12, compilação e testes.

## Licença

Distribuído sob a licença MIT; consulte [`LICENSE`](LICENSE).
