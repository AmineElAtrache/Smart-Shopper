# Plan de Rapport PFA — Smart Shopper / Dalil Souq (Version Pro)

> **Document:** proposition de plan détaillé pour le rapport final de PFA  
> **Projet:** Smart Shopper — assistant intelligent de recherche, comparaison et recommandation de produits au Maroc  
> **Version:** 2.0 (alignée sur l’implémentation réelle du dépôt)  
> **Date de révision:** juin 2026  

---

## 0. Méthode d’audit et résultats

### 0.1 Ce qui a été fait

1. Lecture du plan initial : `Plan_Rapport_PFA_Smart_Shopper (1).docx`
2. Comparaison avec le code source du dépôt `Smart-Shopper`
3. Croisement avec :
   - `PFA_PROJECT_FULL_OVERVIEW.md`
   - `docs/PROJECT_ARCHITECTURE_GUIDE.md`
   - `docs/IMPLEMENTED_PLAN_EXPLANATION.md`
   - agents, mémoire, tests unitaires, déploiement

### 0.2 Résultat principal

Le plan initial (v1) est **structurellement bon** (10 chapitres + intro + conclusion + annexes), mais il décrit surtout un **MVP centré NER + scraping + ranking**.

Le projet réel est aujourd’hui un **système intelligent complet** :

| Dimension | Plan v1 | Projet réel (v2) |
|-----------|---------|------------------|
| Fournisseurs | ~14 sites | **17 providers** |
| NLP | Modèle NER | NER + vocabulaire + intent gate + enrichment LLM + site detection |
| Orchestration | Orchestrator simple | Branches : chat / cache hit / scrape / watch |
| Mémoire | Redis + Mongo (concept) | **3 tiers** avec règles read/write documentées |
| Décision | Scoring | Scoring + filtrage accessoires + city/color + dedup + fraude |
| Génération | Template + LLM | + validation + modération + Darija UX |
| Gouvernance | Liste de features | Policy engine concret (PII, rate limit, robots, quarantine) |
| Tests | Générique | **319 tests unitaires**, 49 fichiers de test |
| Déploiement | Cible AWS | Docker Compose + K8s + CI + cible AWS |

### 0.3 Décision de rédaction

**Conserver la structure en 10 chapitres**, mais :

- Ajouter les **parties préliminaires académiques** (résumé, abstract, acronymes…)
- **Épaissir** les chapitres III, IV, VI, VII, VIII, X
- **Mettre à jour** les chiffres, composants et limites
- Ajouter une section **Problèmes rencontrés & corrections** (preuve de maturité ingénierie)
- Positionner le projet comme **plateforme d’achat intelligent**, pas seulement un modèle NLP

---

## 1. Vue d’ensemble du rapport (nouvelle version)

### 1.1 Objectif du rapport

Présenter la conception, l’implémentation et l’évaluation d’un assistant d’achat intelligent capable de :

- Comprendre des requêtes en **Darija, français et anglais** (souvent mélangés)
- Extraire produit, marque, budget, ville, couleur, intention
- Router la recherche vers **17 marketplaces marocaines**
- Classer et filtrer les offres (y compris accessoires et bruit)
- Générer une réponse personnalisée sur **Telegram**
- Surveiller les prix en arrière-plan (ambient watch)
- Appliquer gouvernance, sécurité et observabilité

### 1.2 Public cible

- Binôme PFA
- Encadrants académiques
- Jury
- Éventuellement partenaire technique / entreprise

### 1.3 Message clé pour le jury

> Smart Shopper n’est pas un chatbot générique ni un simple scraper : c’est une **architecture multi-agents event-driven** combinant NLP multilingue, collecte web, décision intelligente, mémoire à 3 niveaux, génération contrôlée par LLM et gouvernance opérationnelle.

### 1.4 Longueur cible recommandée

| Bloc | Pages (indicatif) |
|------|-------------------|
| Partie préliminaire | 4–6 |
| Introduction | 6–8 |
| Chapitres I–X | 115–140 |
| Conclusion | 4–6 |
| Annexes | 15–25 |
| **Total** | **~140–175 pages** |

---

## 2. Partie préliminaire (À AJOUTER — absent du plan v1)

### 2.1 Page de garde

- Titre complet du projet
- Sous-titre : *Assistant d’achat intelligent basé sur une architecture multi-agents*
- Établissement, filière, année universitaire
- Noms des étudiants (binôme)
- Encadrants
- Date de soutenance

### 2.2 Dédicace (optionnelle)

### 2.3 Remerciements

- Encadrants, jury, famille, ressources open source (Hugging Face, Open Facts…)

### 2.4 Résumé (français) — **OBLIGATOIRE**

**Contenu à couvrir (1 page max) :**

- Contexte : fragmentation des offres e-commerce au Maroc
- Problème : langage naturel bruité, multi-sites, faux positifs (accessoires)
- Solution : pipeline Kafka multi-agents + NER XLM-RoBERTa + scraping parallèle + scoring + LLM validé
- Résultats : 17 providers, pipeline Telegram bout-en-bout, 319 tests unitaires
- Mots-clés : NLP, NER, multi-agents, Kafka, web scraping, recommandation, Darija, e-commerce

### 2.5 Abstract (anglais) — **OBLIGATOIRE**

Traduction structurée du résumé (1 page max).

### 2.6 Liste des acronymes et abréviations

Exemples : NER, NLP, LLM, API, gRPC, PII, MAD, UX, CI/CD, EKS, MSK, Redis, MongoDB, Kafka, HF, Darija, Arabizi…

### 2.7 Liste des figures

Numérotation centralisée (Fig. 1, Fig. 2…).

### 2.8 Liste des tableaux

Numérotation centralisée (Tab. 1, Tab. 2…).

### 2.9 Table des matières

### 2.10 Liste des annexes

---

## 3. Introduction générale (enrichie)

### 3.1 Contexte général

- Croissance e-commerce au Maroc (Jumia, Avito, Electroplanet, Marjane, etc.)
- Difficulté utilisateur : comparer prix, filtres implicites, langues mixtes
- Intérêt d’un assistant conversationnel sur Telegram

### 3.2 Problématique

- Requêtes incomplètes ou bruitées (`chi telaja`, `bghit phone blanc b 3000dh`)
- Entités implicites (ville, budget hérité du contexte)
- Hétérogénéité des sites (HTML, anti-bot, city/color support)
- Risque de mauvaises recommandations (accessoires, SmartTag au lieu de téléphone)

### 3.3 Motivation du projet

- Réduire l’effort de recherche manuelle
- Proposer une expérience locale (Darija + MAD + villes marocaines)
- Démontrer une architecture logicielle scalable pour un PFA

### 3.4 Objectifs du projet

**Objectifs fonctionnels**

- Recevoir une requête utilisateur (Telegram)
- Extraire et enrichir les entités (produit, marque, budget, ville, couleur)
- Router vers les bons sites et scraper en parallèle
- Classer, filtrer et recommander les meilleures offres
- Générer une réponse multilingue (Darija / FR / EN)
- Surveiller les prix (ambient watch)
- Appliquer gouvernance et modération

**Objectifs techniques**

- Architecture event-driven découplée (Kafka)
- Contrats de données stricts (Pydantic)
- Mémoire à 3 niveaux
- Tests automatisés et déploiement reproductible
- Observabilité et audit

### 3.5 Périmètre et hors périmètre — **NOUVEAU**

| Inclus | Exclu (v1 / perspective) |
|--------|--------------------------|
| Telegram MVP | WhatsApp production |
| 17 marketplaces | Paiement / checkout |
| Ranking + réponse | Application mobile native |
| Price watch | Fine-tuning NER custom complet |
| Gouvernance de base | Scraping réseaux sociaux (deferred) |

### 3.6 Contributions principales — **NOUVEAU**

1. Pipeline NLP **hybride** : modèle HF + vocabulaire + règles Darija + fuzzy matching
2. **Routage intelligent** 17 providers + détection site utilisateur (rules / NER / LLM)
3. **Mémoire 3 tiers** : cache global, préférences utilisateur, profil comportemental generator
4. **Filtrage accessoires** et bruit marketplace (`shared/product_matching.py`)
5. **Intent gate** : distinction chat vs recherche produit
6. **Génération LLM contrôlée** : validation, fallback template, modération
7. **Gouvernance** : PII, rate limiting, robots.txt, quarantaine URLs
8. **Ambient scheduler** : surveillance prix avec notification sur baisse

### 3.7 Méthodologie de travail

- Approche itérative (MVP → enrichissements)
- Contrats partagés (`shared/events/schemas.py`)
- Tests unitaires par module
- Documentation + CI
- Corrections guidées par cas réels Telegram

### 3.8 Organisation du rapport

Tableau **Chapitre → Module code → Responsable rédaction** (à remplir par le binôme).

---

## 4. Chapitre I — État de l’art

### 4.1 Introduction

### 4.2 Assistants conversationnels intelligents

- Chatbots génériques vs assistants orientés tâche
- Limites des LLM seuls sans grounding marketplace

### 4.3 Traitement automatique du langage naturel (NLP)

- Tokenization, NER, multilinguisme
- Code-switching Darija / FR / EN

### 4.4 Reconnaissance d’entités nommées (NER)

- NER généraliste vs NER domaine shopping
- Modèles multilingues (XLM-RoBERTa)

### 4.5 Systèmes multi-agents

- Agents spécialisés vs monolithe
- Coordination par messages vs appels synchrones

### 4.6 Architectures event-driven (Kafka)

- Découplage, scalabilité, auditabilité
- Comparaison avec REST synchrone

### 4.7 Systèmes de recommandation et comparaison de prix

- Filtrage, scoring multi-critères, diversification sources

### 4.8 Web scraping e-commerce

- httpx / BeautifulSoup / Playwright
- Éthique : robots.txt, rate limiting

### 4.9 LLM pour extraction vs génération — **NOUVEAU**

- Enrichment city/color (JSON strict)
- Génération réponse avec validation anti-hallucination

### 4.10 Analyse comparative des solutions existantes

- Comparatif : moteurs prix, chatbots, scrapers manuels, assistants IA génériques

### 4.11 Conclusion du chapitre

---

## 5. Chapitre II — Analyse et spécification des besoins

### 5.1 Introduction

### 5.2 Présentation générale de Smart Shopper

- Vision, utilisateurs cibles, canal Telegram

### 5.3 Acteurs du système

| Acteur | Rôle |
|--------|------|
| Utilisateur | Envoie requêtes, reçoit recommandations |
| Administrateur / développeur | Configure, monitor, déploie |
| Telegram | Canal messaging |
| Sites e-commerce (17) | Sources de données |
| APIs LLM (Groq, OpenAI, Gemini) | Enrichment / génération optionnelle |
| Kafka / Redis / MongoDB | Infrastructure |

### 5.4 Besoins fonctionnels (liste complète)

**Existant plan v1 + ajouts v2 :**

| ID | Besoin | Priorité |
|----|--------|----------|
| BF1 | Envoyer requête via Telegram | P0 |
| BF2 | Extraire entités (NER + vocabulaire) | P0 |
| BF3 | Distinguer **chat** vs **recherche produit** | P0 — **NOUVEAU** |
| BF4 | Enrichir city/color manquants (LLM optionnel) | P1 — **NOUVEAU** |
| BF5 | Détecter site demandé (`mn jumia`, `bla avito`) | P1 — **NOUVEAU** |
| BF6 | Router catégorie → providers | P0 |
| BF7 | Scraper en parallèle avec timeout | P0 |
| BF8 | Normaliser produits (`RawProduct`) | P0 |
| BF9 | Filtrer accessoires / bruit | P0 — **NOUVEAU** |
| BF10 | Scorer et classer (100 pts) | P0 |
| BF11 | Diversifier sources top 3 | P1 |
| BF12 | Générer réponse (template / LLM) | P0 |
| BF13 | Valider réponse (pas de prix/URL inventés) | P0 — **NOUVEAU** |
| BF14 | Modérer contenu sortant | P1 — **NOUVEAU** |
| BF15 | Cache réponse globale (Tier 1) | P1 |
| BF16 | Mémoriser préférences utilisateur (Tier 2) | P1 |
| BF17 | Personnaliser ton/langue (Tier 3) | P2 |
| BF18 | Surveiller prix (ambient watch) | P1 |
| BF19 | Appliquer gouvernance (PII, rate limit, robots) | P1 |

### 5.5 Besoins non fonctionnels

- **Performance** : latence pipeline acceptable, scraping parallèle
- **Scalabilité** : agents indépendants, Kafka consumer groups
- **Sécurité** : PII, modération, rate limiting
- **Tolérance aux pannes** : timeout provider, fallback mock, DLQ
- **Maintenabilité** : modules par agent, settings `.env`
- **Observabilité** : logs, health checks, métriques
- **Testabilité** : 319 tests unitaires, contrats Pydantic
- **Configurabilité** : feature flags LLM, soft fallbacks city/color

### 5.6 Contraintes techniques

- Sites sans API publique → scraping
- HTML variable → maintenance spiders
- Modèle NER imperfect sur Darija colloquial
- LLM nécessite clé API et validation stricte

### 5.7 Diagrammes UML recommandés — **ÉLARGI**

| Diagramme | Contenu |
|-----------|---------|
| Cas d’utilisation | Search, watch, greet, help, site-specific search |
| Séquence happy path | Telegram → … → reply |
| Séquence cache hit | Orchestrator skip scrape |
| Séquence conversational | Intent gate → LLM chat |
| Séquence ambient watch | Register → tick → notify |
| Activité pipeline | Branches orchestrator |
| Déploiement | Docker / K8s / AWS cible |

### 5.8 Conclusion du chapitre

---

## 6. Chapitre III — Architecture globale du système (CHAPITRE CLÉ)

### 6.1 Introduction

### 6.2 Choix architecturaux

- Event-driven (Kafka) vs couplage fort
- Multi-agents spécialisés
- gRPC pour NER (seul appel synchrone critique)

### 6.3 Vue globale

**Figure obligatoire :** diagramme composants + topics Kafka

```text
Telegram Gateway
  → msg.inbound
  → Orchestrator (+ NER gRPC, intent gate, memory, cache)
  → scrape.task.assigned
  → WebScraping Agent (17 providers)
  → scrape.raw
  → Decision Agent
  → decision.ranked
  → Agent Generator
  → response.outbound
  → Telegram Gateway

Branches parallèles :
  → ambient.watch → Ambient Scheduler → scrape.task.assigned
  → gov.* → Governance Agent
  → price.history, ner.extracted, cache events
```

### 6.4 Description des composants

| Composant | Fichier(s) | Rôle |
|-----------|------------|------|
| User Proxy Gateway | `gateway/telegram_proxy.py` | Entrée/sortie Telegram, historique |
| Kafka Message Bus | `shared/events/kafka.py`, `topics.py` | Bus événementiel |
| Orchestrator Agent | `agents/orchestrator/` | NER, routing, cache, memory, intent |
| NER Model Service | `models/ner/` | gRPC + HF model + vocabulaire |
| Web Scraping Agent | `agents/webscraping/` | 17 spiders, parallélisme |
| Decision Agent | `agents/decision/` | Rank, filter, score |
| Agent Generator | `agents/agent_generator/` | Template / LLM / validation |
| Ambient Scheduler | `agents/ambient_scheduler/` | Price watches |
| Governance Agent | `agents/governance/` | Audit, PII, rate limit, robots |

### 6.5 Modules orchestrator (détail v2) — **NOUVEAU**

| Module | Rôle |
|--------|------|
| `intent_gate.py` | Chat vs product search |
| `conversational_llm.py` | Réponses small-talk |
| `cache_lookup.py` | Cache Redis query → reply |
| `task_router.py` | Entities → `ProductQuery` |
| `provider_router.py` | Category → sites |
| `provider_router_llm.py` | LLM category fallback |
| `site_registry.py` | 17 providers, aliases, domains |
| `site_detector.py` | Rules + NER site detection |
| `site_detector_llm.py` | LLM site fallback |
| `site_router.py` | Strict / preferred policies |
| `provider_capabilities.py` | City/color/category capabilities |
| `entity_enrichment_llm.py` | City/color enrichment |

### 6.6 Couche mémoire — 3 tiers (DÉTAIL OBLIGATOIRE)

#### Tier 1 — Global Shared Memory (Redis)

| Donnée | Clé | Écrit par | Lu par | TTL |
|--------|-----|-----------|--------|-----|
| Cache réponse | `products:query:{hash}` | Agent Generator | Orchestrator | 30 min |
| Historique prix | `prices:query:{hash}` | Decision Agent | (analytics) | liste 100 |
| Site health | `sites:{domain}:health` | Web Scraper | (monitoring) | 15 min |
| robots.txt | `sites:{domain}:robots` | Governance | Governance | 6 h |

#### Tier 2 — Per-User Shared Memory (MongoDB + Redis hot)

| Donnée | Store | Écrit par | Lu par |
|--------|-------|-----------|--------|
| Profil préférences | Mongo `user_profiles` | Orchestrator | Orchestrator |
| Hot profile cache | Redis `user:{id}:profile` | UserMemory | UserMemory |
| Historique | Mongo `user_history` | Gateway + Orchestrator | audit |
| Watches | Mongo `user_watches` | Ambient Scheduler | mirror |

**Règle v2 importante :** budget mémorisé **uniquement pour le même produit** (évite fuite 7000dh laptop → fridge).

#### Tier 3 — Private Behavioral Memory (MongoDB)

| Donnée | Écrit par | Lu par |
|--------|-----------|--------|
| tone, language, preferred_sources | Agent Generator | Agent Generator (LLM prompt) |

### 6.7 Communication inter-agents (Kafka topics)

Documenter chaque topic : producteur, consommateur, payload schema.

### 6.8 Avantages de l’architecture

- Découplage, testabilité, extensibilité providers
- Cache inter-utilisateurs
- Gouvernance transversale

### 6.9 Conclusion du chapitre

---

## 7. Chapitre IV — Traitement du langage naturel et modèle NER

### 7.1 Introduction

### 7.2 Difficultés du langage utilisateur

- Darija Arabizi (`bghit`, `chi`, `telaja`, `kehla`, `casa`)
- Français / anglais / mélange
- Fautes, accents, code-switching

### 7.3 Pipeline NLP complet (v2)

```text
Texte brut
  → strip accents
  → normalize_vocabulary_text (aliases CSV)
  → fuzzy token correction (RapidFuzz)
  → XLM-RoBERTa NER (HF)
  → context entities (rules)
  → merge + select best product/city
  → optional enrichment LLM (city/color)
  → ProductQuery
```

### 7.4 Modèle utilisé

- **XLM-RoBERTa** fine-tuned : `ElAtrachAMINE/darija-ner-xlmroberta`
- Service gRPC : `models/ner/grpc_server.py`
- Backend : `SMART_SHOPPER_NER_BACKEND=auto|hf`

### 7.5 Entités extraites

product, brand, price, budget, currency, city, color, quality, intent, site

### 7.6 Vocabulaire et ressources

| Source | Rôle |
|--------|------|
| `product_vocabulary.csv` | Aliases manuels Darija/FR/EN |
| `external_vocabulary.csv` | Open Food/Beauty/Products Facts |
| `EXTRA_ENTRIES` | Overrides projet (telaja, kehla, air fryer…) |
| `BLOCKED_BRAND_ALIASES` | Stopwords (`chi` ≠ brand Chi) — **NOUVEAU** |

### 7.7 Intent gate — **NOUVEAU**

- `should_run_product_search()`
- Greetings, help questions → conversational path
- Short queries sans intent explicite → block scrape

### 7.8 Entity enrichment LLM — **NOUVEAU**

- Feature flag : `SCRAPE_ENRICH_ENTITIES_LLM`
- Remplit city/color manquants uniquement
- JSON strict, pas d’invention

### 7.9 Site entity detection — **NOUVEAU**

- `detect_site_entities()`, exclude patterns
- Hybrid : rules → NER → LLM fallback

### 7.10 Exemples d’extraction (tableau obligatoire)

| Requête | Entités attendues | Notes |
|---------|-------------------|-------|
| `bghit samsung phone black f casa b 3000dh` | phone, Samsung, black, casablanca, 3000 | happy path |
| `bghit chi hp omen ykone mafayetch 7000dh` | omen, HP, 7000 | clean model name |
| `chi telaja` | fridge, no brand, no budget | memory + chi fix |
| `baghi chi pomada dial chemse` | sunscreen (limité) | cas limite Darija |
| `bghit phone mn jumia` | phone, sites=[jumia] | site strict |
| `slm cv kidayer` | conversational | no scrape |

### 7.11 Limites du NER

- Beauty Darija under-vocabularized
- Modèle peut halluciner (shirt, Chi brand)
- Nécessité couche rules + vocab + validation

### 7.12 Conclusion du chapitre

---

## 8. Chapitre V — Recherche web et collecte des produits

### 8.1 Introduction

### 8.2 Objectif du module scraping

Collecter `RawProduct` normalisés depuis 17 providers en parallèle.

### 8.3 Sites supportés (MISE À JOUR : 17)

| # | Provider | Catégorie typique |
|---|----------|-------------------|
| 1 | Jumia | general |
| 2 | Avito | general / occasion / immo |
| 3 | Electroplanet | electronics |
| 4 | Electrosalam | electronics |
| 5 | Mafiaway Store | general |
| 6 | Moteur.ma | auto |
| 7 | MyMarket | general |
| 8 | UltraPC | laptop / PC |
| 9 | Defacto | fashion |
| 10 | Biougnach | appliances |
| 11 | Marjane | grocery / general |
| 12 | Decathlon | sports |
| 13 | Mubawab | real estate |
| 14 | Ikea | furniture |
| 15 | Palmarosa | beauty — **AJOUT v2** |
| 16 | BringO | general — **AJOUT v2** |
| 17 | PlanetSport | sports — **AJOUT v2** |

### 8.4 Technologies

- httpx (rapide)
- BeautifulSoup (parsing)
- Playwright (sites JS-heavy, ex. Jumia)

### 8.5 Routage intelligent — **ÉLARGI**

- `classify_product()` → category
- `CATEGORY_SITES` mapping
- `prioritize_sites_for_query()` (city/color/category)
- User site strict mode
- LLM router optionnel

### 8.6 Scraping parallèle et résilience

- Semaphore concurrency
- Timeout par provider
- `record_provider_health()` → Tier 1
- Mock fallback si échec total

### 8.7 Normalisation `RawProduct`

- title, price, currency, source, url, availability, seller, rating, metadata

### 8.8 Matrice capabilities — **NOUVEAU (figure)**

Provider × (city filter, color filter, playwright, catégories)

### 8.9 Limites du scraping

- DOM changes, anti-bot, données incomplètes
- Social spider deferred

### 8.10 Conclusion du chapitre

---

## 9. Chapitre VI — Classement, filtrage et recommandation

### 9.1 Introduction

### 9.2 Rôle du Decision Agent

Consomme `scrape.raw`, publie `decision.ranked`.

### 9.3 Pipeline de filtrage (ordre exact) — **NOUVEAU**

1. Déduplication (`dedup_engine.py`)
2. Pertinence produit (`product_matching` + aliases)
3. Négatifs accessoires (SmartTag, buds, coque…)
4. Filtre prix implausible vs budget
5. Filtres city / color (+ soft fallback)
6. Scoring 100 points
7. Diversification sources (max 2/site dans top 3)
8. Pénalité fraude (`fraud_detector.py`)

### 9.4 Système de scoring (/100)

| Critère | Poids approx |
|---------|--------------|
| Prix vs budget | ~40 |
| Confiance source | ~30 |
| Qualité titre / brand / rating | ~20 |
| Disponibilité | ~10 |

### 9.5 Cas d’étude obligatoires

**Cas 1 — SmartTag false positive**

- Query : `bghit phone blanc b 3000dh`
- Erreur : Galaxy SmartTag2 @ 249 MAD
- Cause : alias `galaxy` + pas de filtre accessoire
- Fix : `shared/product_matching.py`

**Cas 2 — Real estate**

- Query : `bghit apartment f casa b 800000dh`
- Filtrage villa vs apartment

**Cas 3 — Air fryer vs MacBook Air**

- Negative terms air fryer category

### 9.6 Exemple complet de classement

Tableau avant/après score pour 5 produits scrapés.

### 9.7 Conclusion du chapitre

---

## 10. Chapitre VII — Génération de réponse et interaction utilisateur

### 10.1 Introduction

### 10.2 Rôle de l’Agent Generator

Consomme `decision.ranked`, publie `response.outbound`.

### 10.3 Double mode génération

| Mode | Quand | Fichiers |
|------|-------|----------|
| Template | Toujours disponible | `darija_copy.py`, `response_copy.py` |
| LLM | Si clé API + produits | `llm_client.py` |

### 10.4 Validation et sécurité — **NOUVEAU**

- `response_validator.py` : pas de prix/URL inventés
- `materialize_llm_response()` : fallback template
- Content moderation outbound

### 10.5 Adaptation langue / ton

- `behavior_analyzer.py` : infer Darija / FR / EN
- Tier 3 behavioral memory
- Darija Arabizi cohérent (`is_coherent_darija`)

### 10.6 Chemins UX

| Chemin | Déclencheur | Réponse |
|--------|-------------|---------|
| Product results | decision.ranked + products | 3 options ranked |
| No results | query ok, 0 products | message différencié budget/color/city |
| Conversational | intent_gate false | conversational_llm |
| Cache hit | orchestrator cache | réponse cached |

### 10.7 Intégration Telegram

- `gateway/telegram_proxy.py`
- Historique Mongo `telegram_history` + Tier 2 `user_history`

### 10.8 Préparation WhatsApp (perspective)

- Abstraction gateway, pas implémenté production

### 10.9 Exemples réponses (annexe screenshots)

### 10.10 Conclusion du chapitre

---

## 11. Chapitre VIII — Gouvernance, sécurité et monitoring

### 11.1 Introduction

### 11.2 Governance Agent

- Consomme topics Kafka transverses
- Publie `gov.audit`, violations

### 11.3 Policy engine — **DÉTAIL**

| Règle | Action possible |
|-------|-----------------|
| PII detected | mask / quarantine |
| Fake URL | quarantine |
| Rate limit user/domain | throttle / halt |
| robots.txt violation | warn / block (strict mode) |
| Content moderation | block outbound |

### 11.4 Observabilité

- Logs structurés par agent
- HealthServer (`/health`, metrics port)
- Prometheus / Grafana (cible)
- Provider health in Redis

### 11.5 Dead-letter queue

- Erreurs Kafka, retry policy

### 11.6 Conclusion du chapitre

---

## 12. Chapitre IX — Implémentation et déploiement

### 12.1 Introduction

### 12.2 Stack technique

Python 3.11+, Kafka, Redis, MongoDB, Hugging Face, Playwright, Docker, Kubernetes, gRPC, Pydantic, pytest

### 12.3 Structure du projet

```text
agents/          # orchestrator, webscraping, decision, generator, governance, ambient
gateway/         # telegram
models/ner/      # serve, grpc, vocabulary
shared/          # events, memory, config, product_matching, query_matching
deploy/          # docker, k8s
tests/unit/      # 49 fichiers, 319 tests
docs/            # architecture, runbook, deployment
```

### 12.4 Configuration `.env` — matrice feature flags

| Variable | Rôle |
|----------|------|
| `SCRAPE_ROUTE_USE_LLM` | LLM category routing |
| `SCRAPE_ENRICH_ENTITIES_LLM` | city/color enrichment |
| `SCRAPE_USER_SITES_ENABLED` | site detection |
| `SCRAPE_USER_SITES_STRICT` | strict site routing |
| `SCRAPE_USER_SITES_LLM` | LLM site fallback |
| `SCRAPE_SOFT_COLOR_FALLBACK` | relax color filter |
| `SCRAPE_SOFT_CITY_FALLBACK` | relax city filter |
| `LLM_PROVIDER` | groq / openai / gemini / template |
| `CACHE_TTL_SECONDS` | Tier 1 cache TTL |

### 12.5 Lancement local

- Docker Compose
- Services individuels (`python -m agents.*`)

### 12.6 Kubernetes

- Manifests `deploy/k8s/`
- Health probes

### 12.7 Cible AWS

- EKS, MSK, ElastiCache, MongoDB Atlas, ECR
- **Statut honnête :** architecture préparée, validation cloud partielle

### 12.8 CI/CD

- GitHub Actions : pytest, docker validation

### 12.9 Conclusion du chapitre

---

## 13. Chapitre X — Tests, résultats et évaluation (CHAPITRE CLÉ)

### 13.1 Introduction

### 13.2 Stratégie de test

- Tests unitaires par module
- Tests intégration memory tiers
- Tests scrapers par provider
- Pas de coverage % formalisé en CI (limite à mentionner)

### 13.3 Inventaire quantitatif — **NOUVEAU**

| Métrique | Valeur |
|----------|--------|
| Fichiers tests unitaires | 49 |
| Tests passants | 319 |
| Providers testés | 17 |
| Modules memory testés | Tier 1, 2, 3 + integration |
| Governance tests | oui |
| Site detector tests | oui |
| Intent gate tests | oui |
| Product matching tests | oui |

### 13.4 Répartition tests par domaine

| Domaine | Fichiers exemple |
|---------|------------------|
| NER / vocab | `test_ner_and_orchestrator.py`, `test_open_facts_vocabulary.py` |
| Orchestrator / intent | `test_orchestrator_intent_gate.py`, `test_entity_enrichment_llm.py` |
| Site routing | `test_site_detector.py`, `test_provider_router.py` |
| Scrapers | `test_jumia_scraper.py`, … (17) |
| Decision | `test_decision_agent.py`, `test_product_matching.py`, `test_scoring_city_color.py` |
| Generator | `test_agent_generator.py`, `test_conversational_llm.py` |
| Memory | `test_memory_tiers.py`, `test_memory_integration.py` |
| Governance | `test_governance_policy_engine.py`, `test_content_moderation.py` |
| Deployment | `test_deployment_readiness.py` |

### 13.5 Cas d’usage réels (tableau d’évaluation)

| ID | Input utilisateur | Résultat attendu | Statut |
|----|-------------------|------------------|--------|
| E1 | `bghit samsung phone black f casa b 3000dh` | entités + scrape + rank | ✅ |
| E2 | `bghit phone blanc b 3000dh` | pas SmartTag/accessoires | ✅ (après fix) |
| E3 | `chi telaja` | fridge, sans budget hérité | ✅ (après fix) |
| E4 | `bghit apartment f casa b 800000dh` | immobilier | ✅ |
| E5 | `bghit phone mn jumia b 3000dh` | sites=jumia | ✅ |
| E6 | `slm cv kidayer` | conversational | ✅ |
| E7 | `baghi chi pomada dial chemse` | sunscreen (partiel) | ⚠️ limite |

### 13.6 Problèmes rencontrés et solutions — **SECTION OBLIGATOIRE**

| Problème | Cause | Solution |
|----------|-------|----------|
| SmartTag recommandé pour phone | alias `galaxy` + pas filtre accessoire | `product_matching.py` |
| Budget 7000 sur fridge après laptop | Tier 2 budget global | budget scoped par produit |
| `chi` → brand Chi | vocab OpenBeautyFacts | `BLOCKED_BRAND_ALIASES` |
| Bot dit "no results" avec 5 produits | filtres city/real-estate | scoring + aliases |
| Darija sunscreen non compris | vocab incomplet | roadmap vocab |

### 13.7 Analyse des résultats

- Précision NER sur échantillon Darija
- Qualité ranking subjective (top 3 pertinents)
- Latence pipeline (mesure si possible)

### 13.8 Limites actuelles

- NER imperfect sur certaines expressions Darija
- Scraping fragile aux changements HTML
- Pas WhatsApp prod
- Pas fine-tune NER custom complet
- Social scraper deferred
- Pas de métrique coverage % CI

### 13.9 Conclusion du chapitre

---

## 14. Conclusion générale

### 14.1 Bilan du projet

- Objectifs atteints vs plan initial MVP
- Passage MVP → système intelligent complet

### 14.2 Apports du projet

- Académiques : multi-agents, NLP multilingue, event-driven
- Techniques : 17 providers, 319 tests, gouvernance
- Pratiques : assistant Telegram utilisable

### 14.3 Difficultés rencontrées

- Langue Darija, scraping, false positives, memory leaks

### 14.4 Perspectives

- WhatsApp gateway
- Application mobile
- Premium price watch
- Plus de fournisseurs
- Fine-tune NER Darija
- RAG sur catalogues
- Déploiement cloud complet (EKS/MSK)
- Métriques production (Grafana, tracing)

### 14.5 Conclusion finale

---

## 15. Annexes recommandées (version pro)

| Annexe | Titre | Contenu |
|--------|-------|---------|
| A | Architecture complète | Diagramme PNG (simulateur HTML ou draw.io) |
| B | Topics Kafka | Liste topics + exemples JSON payloads |
| C | Configuration | `.env.example` commenté |
| D | Extraction NER | 15+ requêtes Darija/FR/EN + entités |
| E | Matrice providers | 17 lignes × capabilities |
| F | Scoring | Exemple détaillé /100 |
| G | Captures Telegram | Avant/après corrections |
| H | Docker / K8s | Extraits manifests |
| I | Tests | Screenshot `pytest` 319 passed |
| J | Structure GitHub | Arborescence repo |
| K | Mapping chapitre → code | Table de traçabilité |
| L | Glossaire Darija | telaja, bghit, chi, kehla, casa… |
| M | Proto gRPC NER | `proto/ner.proto` |
| N | Feature flags | Table SCRAPE_* / LLM_* |

---

## 16. Répartition rédaction suggérée (binôme)

| Chapitres | Thème | Modules code |
|-----------|-------|--------------|
| Étudiant A | NLP, NER, vocab, intent | `models/ner/`, `intent_gate`, enrichment |
| Étudiant B | Scraping, routing, providers | `webscraping/`, `provider_router`, `site_*` |
| Étudiant A | Decision, filtering | `decision/`, `product_matching` |
| Étudiant B | Generator, Telegram UX | `agent_generator/`, `gateway/` |
| **Commun** | Architecture, memory, tests, conclusion | `shared/memory/`, tests, docs |

*(Adapter selon répartition réelle du binôme.)*

---

## 17. Checklist avant soumission du rapport

- [ ] Résumé FR + Abstract EN rédigés
- [ ] Liste acronymes complète
- [ ] 17 providers (pas 14) partout dans le texte
- [ ] Diagramme architecture avec branches (chat / cache / scrape / watch)
- [ ] Table mémoire 3 tiers avec read/write
- [ ] Section intent gate + conversational path
- [ ] Section site detection hybrid
- [ ] Section product_matching / accessoires
- [ ] Tableau 319 tests + répartition domaines
- [ ] Cas réels Telegram (6–10 exemples)
- [ ] Section problèmes & solutions (bugs réels)
- [ ] Section limites honnêtes
- [ ] Annexes K (mapping code) + captures
- [ ] Cohérence figures/tableaux numérotés
- [ ] Bibliographie (Kafka, HF, Playwright, articles NLP multilingue)

---

## 18. Bibliographie indicative (à compléter)

- Documentation Apache Kafka
- Hugging Face Transformers / XLM-RoBERTa
- Open Food Facts / Open Beauty Facts
- Playwright, httpx, BeautifulSoup docs
- Articles : NER multilingue, event-driven microservices, ethical web scraping
- Documentation Telegram Bot API

---

## 19. Synthèse des changements v1 → v2

| Zone | v1 | v2 (ce document) |
|------|----|--------------------|
| Partie préliminaire | Absente | Résumé, Abstract, acronymes, listes |
| Introduction | Basique | Périmètre, contributions, méthodologie |
| Architecture | Agents listés | + intent gate, site router, enrichment, memory detail |
| NLP | Modèle HF | Pipeline hybride complet |
| Scraping | 14 sites | 17 sites + capabilities matrix |
| Decision | Scoring | Pipeline filtrage + cas SmartTag |
| Generator | Template/LLM | + validation + moderation + Darija |
| Governance | Liste | Policy engine détaillé |
| Tests | Générique | 319 tests, cas E1–E7, bugs documentés |
| Annexes | Basiques | 14 annexes pro + mapping code |

---

*Fin du plan de rapport PFA — Smart Shopper v2.0 Pro*
