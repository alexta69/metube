# Local-only Docker profile

この構成は、MeTube をローカルPCからのみ使うための Docker 起動プロファイルです。対象は、自分の動画、許可済み動画、または合法利用できる動画だけです。Web公開、外部ユーザーへの提供、広告収益化、アクセス制限の回避を目的にしません。

コンテナはホスト側の loopback interface のみに公開します。

```text
http://127.0.0.1:8081/
```

## 起動

```powershell
docker compose -f docker-compose.local.yml up -d
```

ブラウザでは次のURLを開きます。

```text
http://127.0.0.1:8081/
```

同じPC上では `http://localhost:8081/` でもアクセスできる想定です。

## 停止

```powershell
docker compose -f docker-compose.local.yml down
```

## ログ確認

```powershell
docker compose -f docker-compose.local.yml logs --tail=80
```

## PowerShellでのポート確認

PowerShellで、待ち受けがローカル専用になっていることを確認します。

```powershell
Get-NetTCPConnection -LocalPort 8081 | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

`LocalAddress` が `127.0.0.1` であることを確認します。`0.0.0.0` やLAN IPで待ち受けている場合は、利用せずに停止して compose 設定を修正してください。

ローカルアクセスは次のコマンドでも確認できます。

```powershell
curl http://127.0.0.1:8081/
curl http://localhost:8081/
```

## この構成で使わないもの

このローカル専用プロファイルでは、reverse proxy、HTTPS、`PUBLIC_HOST_URL`、browser extension、CORS `*` は使いません。

このリポジトリに cookie、token、secret を保存・表示しないでください。DRM回避、認証突破、制限回避、大量取得最適化は対象外です。

## 検証済み環境

- 検証日: 2026-06-06
- 実行環境: Windows + Docker Desktop
- `docker compose -f docker-compose.local.yml config`: `host_ip: 127.0.0.1` を確認
- `http://127.0.0.1:8081/`: アクセス確認済み
- `http://localhost:8081/`: アクセス確認済み
- `Get-NetTCPConnection -LocalPort 8081`: `LocalAddress` が `127.0.0.1` であることを確認
- `docker compose -f docker-compose.local.yml down`: 停止確認済み
