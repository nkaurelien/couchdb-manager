#!/bin/bash
# CouchDB Manager - Installation Script

set -e

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     CouchDB Manager Installer      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════╝${NC}"
echo ""

# Check Python
echo -e "${YELLOW}Vérification de Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 n'est pas installé${NC}"
    echo "Veuillez installer Python 3.8 ou supérieur"
    exit 1
fi
echo -e "${GREEN}✓ Python $(python3 --version)${NC}"

# Check pip
echo -e "${YELLOW}Vérification de pip...${NC}"
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip n'est pas installé${NC}"
    echo "Installation de pip..."
    python3 -m ensurepip --default-pip
fi
echo -e "${GREEN}✓ pip installé${NC}"

# Create virtual environment
echo -e "${YELLOW}Création de l'environnement virtuel...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Environnement virtuel créé${NC}"
else
    echo -e "${GREEN}✓ Environnement virtuel existant${NC}"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installation des dépendances...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✓ Dépendances installées${NC}"

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Création du fichier de configuration...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ Fichier .env créé${NC}"
    echo -e "${YELLOW}⚠ N'oubliez pas de configurer vos identifiants dans .env${NC}"
else
    echo -e "${GREEN}✓ Fichier .env existant${NC}"
fi

# Create backups directory
if [ ! -d "backups" ]; then
    mkdir -p backups
    echo -e "${GREEN}✓ Dossier de backups créé${NC}"
fi

# Make scripts executable
chmod +x manage/*.sh 2>/dev/null || true

echo ""
echo -e "${GREEN}╔════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    Installation terminée ! 🎉      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════╝${NC}"
echo ""
echo "Pour lancer l'application :"
echo -e "  ${YELLOW}source venv/bin/activate${NC}"
echo -e "  ${YELLOW}streamlit run couchdb_manager.py${NC}"
echo ""
echo "Ou utilisez le Makefile :"
echo -e "  ${YELLOW}make run${NC}"
echo ""