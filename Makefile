# CouchDB Manager - Makefile
# Commandes utiles pour gérer l'application CouchDB Manager

.PHONY: help install run dev clean test backup restore sync setup check-env docker-run docker-build

# Variables
PYTHON := python3
PIP := pip3
STREAMLIT := streamlit
APP := couchdb_manager.py
PORT := 8501
BACKUP_DIR := ./backups

# Couleurs pour l'affichage
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

## help: Affiche cette aide
help:
	@echo "${GREEN}CouchDB Manager - Commandes disponibles${NC}"
	@echo ""
	@grep -E '^##' Makefile | sed 's/## //'
	@echo ""

## install: Installe les dépendances Python
install:
	@echo "${YELLOW}Installation des dépendances...${NC}"
	$(PIP) install -r requirements.txt
	@echo "${GREEN}✓ Installation terminée${NC}"

## setup: Configure l'environnement initial
setup: install
	@echo "${YELLOW}Configuration de l'environnement...${NC}"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "${GREEN}✓ Fichier .env créé à partir de .env.example${NC}"; \
		echo "${YELLOW}⚠ N'oubliez pas de configurer vos identifiants dans .env${NC}"; \
	else \
		echo "${YELLOW}✓ Fichier .env déjà existant${NC}"; \
	fi
	@if [ ! -d $(BACKUP_DIR) ]; then \
		mkdir -p $(BACKUP_DIR); \
		echo "${GREEN}✓ Dossier de backups créé${NC}"; \
	fi

## run: Lance l'application Streamlit
run: check-env
	@echo "${GREEN}Lancement de CouchDB Manager...${NC}"
	$(STREAMLIT) run $(APP) --server.port $(PORT)

## dev: Lance l'application en mode développement avec rechargement automatique
dev: check-env
	@echo "${GREEN}Lancement en mode développement...${NC}"
	$(STREAMLIT) run $(APP) --server.port $(PORT) --server.runOnSave true

## check-env: Vérifie que l'environnement est configuré
check-env:
	@if [ ! -f .env ]; then \
		echo "${RED}❌ Erreur: Fichier .env non trouvé${NC}"; \
		echo "${YELLOW}Exécutez 'make setup' pour créer le fichier .env${NC}"; \
		exit 1; \
	fi
	@echo "${GREEN}✓ Configuration vérifiée${NC}"

## clean: Nettoie les fichiers temporaires et cache
clean:
	@echo "${YELLOW}Nettoyage...${NC}"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".DS_Store" -delete 2>/dev/null || true
	@if [ -d .streamlit ]; then rm -rf .streamlit; fi
	@echo "${GREEN}✓ Nettoyage terminé${NC}"

## test-connection: Teste la connexion aux serveurs CouchDB
test-connection: check-env
	@echo "${YELLOW}Test de connexion aux serveurs CouchDB...${NC}"
	@$(PYTHON) -c "import os; from dotenv import load_dotenv; import requests; \
		load_dotenv(); \
		source_url = os.getenv('SOURCE_COUCHDB_URL'); \
		target_url = os.getenv('TARGET_COUCHDB_URL'); \
		print('Test connexion SOURCE:', source_url); \
		try: \
			r = requests.get(source_url, timeout=5); \
			print('✓ SOURCE accessible'); \
		except: \
			print('❌ SOURCE inaccessible'); \
		print('Test connexion TARGET:', target_url); \
		try: \
			r = requests.get(target_url, timeout=5); \
			print('✓ TARGET accessible'); \
		except: \
			print('❌ TARGET inaccessible')"

## list-backups: Liste tous les backups disponibles
list-backups:
	@echo "${GREEN}Backups disponibles:${NC}"
	@if [ -d $(BACKUP_DIR) ]; then \
		ls -la $(BACKUP_DIR) 2>/dev/null || echo "Aucun backup trouvé"; \
	else \
		echo "${YELLOW}Dossier de backups non trouvé${NC}"; \
	fi

## backup-clean: Supprime les backups de plus de 7 jours
backup-clean:
	@echo "${YELLOW}Suppression des anciens backups (>7 jours)...${NC}"
	@if [ -d $(BACKUP_DIR) ]; then \
		find $(BACKUP_DIR) -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true; \
		echo "${GREEN}✓ Nettoyage terminé${NC}"; \
	else \
		echo "${YELLOW}Dossier de backups non trouvé${NC}"; \
	fi

## docker-build: Construit l'image Docker
docker-build:
	@echo "${YELLOW}Construction de l'image Docker...${NC}"
	docker build -t couchdb-manager:latest .
	@echo "${GREEN}✓ Image construite${NC}"

## docker-run: Lance l'application dans Docker
docker-run:
	@echo "${GREEN}Lancement du conteneur Docker...${NC}"
	docker run -d \
		--name couchdb-manager \
		-p $(PORT):$(PORT) \
		-v $(PWD)/backups:/app/backups \
		-v $(PWD)/.env:/app/.env \
		couchdb-manager:latest

## docker-stop: Arrête et supprime le conteneur
docker-stop:
	@echo "${YELLOW}Arrêt du conteneur...${NC}"
	docker stop couchdb-manager 2>/dev/null || true
	docker rm couchdb-manager 2>/dev/null || true
	@echo "${GREEN}✓ Conteneur arrêté${NC}"

## update: Met à jour les dépendances
update:
	@echo "${YELLOW}Mise à jour des dépendances...${NC}"
	$(PIP) install --upgrade -r requirements.txt
	@echo "${GREEN}✓ Mise à jour terminée${NC}"

## version: Affiche les versions des outils
version:
	@echo "${GREEN}Versions des outils:${NC}"
	@$(PYTHON) --version
	@$(PIP) --version
	@$(STREAMLIT) --version
	@echo "CouchDB Manager: v1.0.0"

## logs: Affiche les logs de l'application
logs:
	@echo "${GREEN}Logs récents:${NC}"
	@if [ -f streamlit.log ]; then \
		tail -n 50 streamlit.log; \
	else \
		echo "${YELLOW}Aucun fichier de log trouvé${NC}"; \
	fi

## env-example: Affiche un exemple de configuration .env
env-example:
	@echo "${GREEN}Exemple de configuration .env:${NC}"
	@cat .env.example

# Alias pour les commandes courantes
start: run
stop: docker-stop
restart: docker-stop docker-run

# Commande par défaut
.DEFAULT_GOAL := help