.PHONY: serve-dev build build-dev attach-dev-frontend attach-dev-backend

serve-dev:
	docker-compose up

attach-dev-frontend:
	docker exec -it -t metube-dev-frontend /bin/sh

attach-dev-backend:
	docker exec -it -t metube-dev-backend /bin/sh

build-dev:
	docker-compose build

build:
	docker build -t metube .
