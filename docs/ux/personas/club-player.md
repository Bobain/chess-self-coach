# Marc, le compétiteur de club

**Elo** : ~1600-1900
**Archetype** : Competitor — tournament preparation and opening drilling

## Profile

Joue en club et participe à des tournois régulièrement. A un répertoire d'ouvertures structuré (Sicilienne Najdorf en noir, 1.d4 en blanc par exemple). Utilise En-Croissant et Chessbase/ChessBase Reader pour préparer ses ouvertures. Compte chess.com gratuit ou premium — dans les deux cas, trouve les outils d'ouverture de chess.com limités pour une vraie préparation de tournoi.

## Goal

Préparer ses ouvertures avant un tournoi. Identifier son répertoire réel à partir de ses parties chess.com (quelles lignes joue-t-il en pratique ?), creuser les variantes critiques, et driller les lignes pour les avoir en mémoire musculaire le jour du tournoi.

## Observed behavior

- Avant un tournoi, passe des heures à réviser ses lignes d'ouverture
- Veut voir ses stats par ouverture : quel score avec la Najdorf ? Où perd-il le plus souvent ?
- Cherche les lignes où ses adversaires de club dévient de la théorie (preparation surprise)
- Alterne entre étude (explorer l'arbre de variantes) et drill (jouer les coups de mémoire)
- Compare les lignes jouées dans ses parties avec les lignes théoriques

## Frustrations with current UI

- Pas de fonctionnalité "opening preparation" — le training porte uniquement sur les erreurs en milieu/fin de partie
- Pas de vue répertoire (arbre de variantes visuel avec ses lignes habituelles)
- Les données d'ouverture sont là (Opening Explorer data dans analysis_data.json) mais pas exploitables dans l'UI
- Pas de filtre par ouverture dans le game review
- Pas de mode drill spécifique aux ouvertures (jouer les coups du répertoire contre un sparring)

## What would help

- Un répertoire extrait automatiquement de ses parties chess.com (les ouvertures qu'il joue réellement)
- Un arbre de variantes interactif montrant ses lignes habituelles + fréquence + résultat
- Un mode drill d'ouverture : l'app joue les coups adverses, il doit trouver ses réponses théoriques
- La possibilité de creuser une ligne spécifique (sub-variations, transpositions)
- Un filtre "préparation tournoi" qui cible les ouvertures probables contre un adversaire spécifique (basé sur leurs parties)
- Intégration avec l'Opening Explorer Lichess pour enrichir les lignes

## Usage pattern

Desktop, sessions longues (30-60 min) en préparation de tournoi. Utilise aussi le game review et le training mais son besoin principal est la préparation d'ouvertures. Mobile pour réviser rapidement ses lignes le jour du tournoi.
