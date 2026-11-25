Image Docker du dashboard fast-n-fourgon, construite par le CI depuis le commit ${SHORT_SHA}.

### Lancer cette version

Avec Docker (Docker Desktop sous Windows ou macOS) :

```bash
docker run -d --name fast-n-fourgon -p 8501:8501 -v fast-n-fourgon-historique:/app/data/historique ${IMAGE}:${VERSION}
```

puis ouvrir http://localhost:8501. L'historique des runs reste dans le volume `fast-n-fourgon-historique`.

### Sans accès à ghcr.io

Télécharger ci-dessous l'archive de sa machine (`amd64` : PC Windows ou Linux, Mac Intel ; `arm64` : Mac Apple
Silicon), puis :

```bash
docker load -i fast-n-fourgon-${VERSION}-linux-amd64.tar.gz
```

et lancer la même commande `docker run`. Le fichier `SHA256SUMS` donne l'empreinte de chaque archive.
