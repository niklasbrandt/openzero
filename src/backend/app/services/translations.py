"""
Translations Service
--------------------
Single source of truth for all user-facing strings in the openZero system.
Covers dashboard widget labels, Planka entity names (project/board/list),
and UI states. Each language dict is keyed by the same string IDs.

When a user changes their language, the backend serves these translations
via /api/dashboard/translations and optionally renames Planka entities
via the PATCH API.
"""

from typing import Optional

# ── Translation dictionaries ────────────────────────────────────────────
# Start with en + de as first-class citizens. Other languages follow the
# same structure and fall back to English for any missing key.

_EN = {
    # ── Planka entity names ──
    "project_name": "Operations",
    "board_name": "Operator Board",
    "list_today": "Today",
    "list_this_week": "This Week",
    "list_backlog": "Backlog",
    "list_done": "Done",
    "list_inbox": "Inbox",

    # ── LifeOverview ──
    "life_overview": "Life Overview",
    "mapping_world": "Mapping your world...",
    "boards_heading": "Boards",
    "new_board": "+ New Board",
    "inner_circle": "Inner Circle",
    "inner_subtitle": "Family & Care",
    "close_circle": "Close Circle",
    "close_subtitle": "Friends & Social",
    "timeline_heading": "Timeline (Next 3 Days)",
    "no_family": "No family connections.",
    "no_social": "No social circle added.",
    "no_events": "No upcoming events for the next 3 days.",
    "initializing_projects": "Initializing projects...",
    "api_error_life": "Unable to load Life Overview. Check backend connection.",

    # ── HardwareMonitor ──
    "hardware": "Hardware",
    "hw_subtitle": "CPU & SIMD Capabilities",
    "detecting_hw": "Detecting hardware...",
    "hw_error": "Could not reach hardware probe. Is the backend running?",
    "cores": "Cores",
    "arch": "Arch",
    "platform": "Platform",
    "simd": "SIMD",
    "excellent_hw": "Well-suited for local LLM inference",
    "good_hw": "Adequate for small-to-medium models",
    "limited_hw": "Limited -- expect slow inference on larger models",
    "tip_cpu_model": "CPU model string as reported by the kernel",
    "tip_cores": "Physical cores run actual computations. Logical cores (hyperthreads) help with scheduling but add less throughput for LLM workloads.",
    "tip_arch": "CPU instruction set architecture. x86_64 supports the widest range of SIMD extensions for llama.cpp.",
    "tip_platform": "Host operating system running the Docker containers.",
    "tip_simd": "SIMD (Single Instruction, Multiple Data) extensions allow the CPU to process multiple values in parallel. Higher SIMD = faster LLM inference.",
    "tip_sse42": "Baseline SIMD. Used by all modern llama.cpp builds for basic vectorized math.",
    "tip_avx2": "Advanced Vector Extensions 2. Doubles throughput for quantized matrix ops. Critical for good tok/s on CPU.",
    "tip_avx512": "Widest SIMD. Up to 2x faster than AVX2 for large quantized models. Rare on consumer CPUs, common on EPYC/Xeon.",

    # ── SystemBenchmark ──
    "llm_benchmark": "LLM Benchmark",
    "bench_subtitle": "Throughput & Performance Rating",
    "bench_empty": "Click a tier button to measure tokens/second.",
    "bench_instant": "Bench instant",
    "bench_standard": "Bench standard",
    "bench_deep": "Bench deep",
    "bench_run_all": "Run All",
    "excellent": "Excellent",
    "good": "Good",
    "moderate": "Moderate",
    "slow": "Slow",
    "tip_bench_instant": "Benchmark the instant tier (~3-4B model). Used for quick tasks like fact extraction and classification.",
    "tip_bench_standard": "Benchmark the standard tier (~8B model). Used for general conversation and reasoning.",
    "tip_bench_deep": "Benchmark the deep tier (~14B model). Used for complex analysis and strategic thinking.",
    "tip_bench_all": "Run all three tier benchmarks sequentially to get a complete performance picture.",
    "tip_legend": "Performance rating scale based on expected throughput for each model size on CPU-only inference with Q4_K_M quantization.",
    "tip_legend_excellent": "Fast real-time conversation. No noticeable delay between tokens.",
    "tip_legend_good": "Comfortable interactive speed with slight streaming visible.",
    "tip_legend_moderate": "Usable but noticeable word-by-word generation.",
    "tip_legend_slow": "Below expected. Check SIMD, thread count, or try a smaller model.",

    # ── UserCard (static labels) ──
    "edit": "Edit",
    "save_profile": "Save Profile",
    "discard": "Discard",
    "birthday": "Birthday",
    "gender": "Gender",
    "residency": "Residency",
    "town": "Town",
    "country": "Country",
    "timezone_label": "Timezone",
    "briefing_time": "Briefing Time",
    "language_label": "Language",
    "work_times": "Typical Work Times",
    "life_goals": "Life Goals & Core Values",
    "no_goals": "No goals set.",
    "not_set": "Not set",
}

_DE = {
    # ── Planka entity names ──
    "project_name": "Operationen",
    "board_name": "Operator-Board",
    "list_today": "Heute",
    "list_this_week": "Diese Woche",
    "list_backlog": "Backlog",
    "list_done": "Erledigt",
    "list_inbox": "Eingang",

    # ── LifeOverview ──
    "life_overview": "Lebensuebersicht",
    "mapping_world": "Deine Welt wird geladen...",
    "boards_heading": "Boards",
    "new_board": "+ Neues Board",
    "inner_circle": "Innerer Kreis",
    "inner_subtitle": "Familie & Fuersorge",
    "close_circle": "Enger Kreis",
    "close_subtitle": "Freunde & Soziales",
    "timeline_heading": "Zeitplan (Naechste 3 Tage)",
    "no_family": "Keine Familienverbindungen.",
    "no_social": "Kein sozialer Kreis hinzugefuegt.",
    "no_events": "Keine Termine in den naechsten 3 Tagen.",
    "initializing_projects": "Projekte werden initialisiert...",
    "api_error_life": "Lebensuebersicht konnte nicht geladen werden. Backend-Verbindung pruefen.",

    # ── HardwareMonitor ──
    "hardware": "Hardware",
    "hw_subtitle": "CPU- & SIMD-Faehigkeiten",
    "detecting_hw": "Hardware wird erkannt...",
    "hw_error": "Hardware-Probe nicht erreichbar. Laeuft das Backend?",
    "cores": "Kerne",
    "arch": "Architektur",
    "platform": "Plattform",
    "simd": "SIMD",
    "excellent_hw": "Gut geeignet fuer lokale LLM-Inferenz",
    "good_hw": "Ausreichend fuer kleine bis mittlere Modelle",
    "limited_hw": "Eingeschraenkt -- erwarte langsame Inferenz bei groesseren Modellen",
    "tip_cpu_model": "CPU-Modell laut Kernel",
    "tip_cores": "Physische Kerne fuehren Berechnungen aus. Logische Kerne (Hyperthreads) helfen bei Scheduling, bringen aber weniger Durchsatz fuer LLM-Workloads.",
    "tip_arch": "CPU-Befehlssatzarchitektur. x86_64 unterstuetzt die meisten SIMD-Erweiterungen fuer llama.cpp.",
    "tip_platform": "Host-Betriebssystem, auf dem die Docker-Container laufen.",
    "tip_simd": "SIMD (Single Instruction, Multiple Data) erlaubt parallele Verarbeitung mehrerer Werte. Mehr SIMD = schnellere LLM-Inferenz.",
    "tip_sse42": "Basis-SIMD. Wird von allen modernen llama.cpp-Builds fuer grundlegende vektorisierte Mathematik verwendet.",
    "tip_avx2": "Advanced Vector Extensions 2. Verdoppelt den Durchsatz fuer quantisierte Matrix-Operationen. Kritisch fuer gute tok/s auf CPU.",
    "tip_avx512": "Breitestes SIMD. Bis zu 2x schneller als AVX2 fuer grosse quantisierte Modelle. Selten bei Consumer-CPUs, haeufig bei EPYC/Xeon.",

    # ── SystemBenchmark ──
    "llm_benchmark": "LLM-Benchmark",
    "bench_subtitle": "Durchsatz & Leistungsbewertung",
    "bench_empty": "Klicke auf eine Tier-Schaltflaeche, um Tokens/Sekunde zu messen.",
    "bench_instant": "Bench Instant",
    "bench_standard": "Bench Standard",
    "bench_deep": "Bench Deep",
    "bench_run_all": "Alle starten",
    "excellent": "Exzellent",
    "good": "Gut",
    "moderate": "Maessig",
    "slow": "Langsam",
    "tip_bench_instant": "Benchmark des Instant-Tiers (~3-4B Modell). Fuer schnelle Aufgaben wie Faktenextraktion und Klassifikation.",
    "tip_bench_standard": "Benchmark des Standard-Tiers (~8B Modell). Fuer allgemeine Konversation und Schlussfolgerung.",
    "tip_bench_deep": "Benchmark des Deep-Tiers (~14B Modell). Fuer komplexe Analyse und strategisches Denken.",
    "tip_bench_all": "Alle drei Tier-Benchmarks nacheinander ausfuehren fuer ein vollstaendiges Leistungsbild.",
    "tip_legend": "Leistungsbewertungsskala basierend auf erwartetem Durchsatz pro Modellgroesse bei CPU-only-Inferenz mit Q4_K_M-Quantisierung.",
    "tip_legend_excellent": "Schnelle Echtzeit-Konversation. Keine spuerbare Verzoegerung zwischen Tokens.",
    "tip_legend_good": "Komfortable interaktive Geschwindigkeit mit leicht sichtbarem Streaming.",
    "tip_legend_moderate": "Nutzbar, aber merkbares Wort-fuer-Wort-Generieren.",
    "tip_legend_slow": "Unter den Erwartungen. SIMD, Thread-Anzahl pruefen oder kleineres Modell verwenden.",

    # ── UserCard ──
    "edit": "Bearbeiten",
    "save_profile": "Profil speichern",
    "discard": "Verwerfen",
    "birthday": "Geburtstag",
    "gender": "Geschlecht",
    "residency": "Wohnort",
    "town": "Stadt",
    "country": "Land",
    "timezone_label": "Zeitzone",
    "briefing_time": "Briefing-Zeit",
    "language_label": "Sprache",
    "work_times": "Typische Arbeitszeiten",
    "life_goals": "Lebensziele & Grundwerte",
    "no_goals": "Keine Ziele gesetzt.",
    "not_set": "Nicht gesetzt",
}

_ES = {
    "project_name": "Operaciones",
    "board_name": "Tablero Operador",
    "list_today": "Hoy",
    "list_this_week": "Esta Semana",
    "list_backlog": "Pendientes",
    "list_done": "Hecho",
    "list_inbox": "Entrada",
    "life_overview": "Vision General",
    "mapping_world": "Mapeando tu mundo...",
    "boards_heading": "Tableros",
    "new_board": "+ Nuevo Tablero",
    "inner_circle": "Circulo Interno",
    "inner_subtitle": "Familia & Cuidado",
    "close_circle": "Circulo Cercano",
    "close_subtitle": "Amigos & Social",
    "timeline_heading": "Linea de Tiempo (Proximos 3 Dias)",
    "no_family": "Sin conexiones familiares.",
    "no_social": "Sin circulo social agregado.",
    "no_events": "Sin eventos proximos para los proximos 3 dias.",
    "initializing_projects": "Inicializando proyectos...",
    "api_error_life": "No se pudo cargar la Vision General. Verifica la conexion del backend.",
    "hardware": "Hardware",
    "hw_subtitle": "Capacidades de CPU y SIMD",
    "detecting_hw": "Detectando hardware...",
    "hw_error": "No se pudo contactar la sonda de hardware. Esta el backend activo?",
    "cores": "Nucleos",
    "arch": "Arquitectura",
    "platform": "Plataforma",
    "simd": "SIMD",
    "excellent_hw": "Bien adaptado para inferencia LLM local",
    "good_hw": "Adecuado para modelos pequenos a medianos",
    "limited_hw": "Limitado -- espere inferencia lenta en modelos mas grandes",
    "llm_benchmark": "Benchmark LLM",
    "bench_subtitle": "Rendimiento y Calificacion",
    "bench_empty": "Haz clic en un boton de tier para medir tokens/segundo.",
    "bench_instant": "Bench instant",
    "bench_standard": "Bench standard",
    "bench_deep": "Bench deep",
    "bench_run_all": "Ejecutar Todo",
    "excellent": "Excelente",
    "good": "Bueno",
    "moderate": "Moderado",
    "slow": "Lento",
    "edit": "Editar",
    "save_profile": "Guardar Perfil",
    "discard": "Descartar",
    "birthday": "Cumpleanos",
    "gender": "Genero",
    "residency": "Residencia",
    "town": "Ciudad",
    "country": "Pais",
    "timezone_label": "Zona Horaria",
    "briefing_time": "Hora de Briefing",
    "language_label": "Idioma",
    "work_times": "Horario Laboral Tipico",
    "life_goals": "Metas de Vida & Valores Fundamentales",
    "no_goals": "Sin metas establecidas.",
    "not_set": "No establecido",
}

_FR = {
    "project_name": "Operations",
    "board_name": "Tableau Operateur",
    "list_today": "Aujourd'hui",
    "list_this_week": "Cette Semaine",
    "list_backlog": "En attente",
    "list_done": "Termine",
    "list_inbox": "Boite de reception",
    "life_overview": "Vue d'ensemble",
    "mapping_world": "Cartographie de votre monde...",
    "boards_heading": "Tableaux",
    "new_board": "+ Nouveau Tableau",
    "inner_circle": "Cercle Interne",
    "inner_subtitle": "Famille & Soins",
    "close_circle": "Cercle Proche",
    "close_subtitle": "Amis & Social",
    "timeline_heading": "Chronologie (3 Prochains Jours)",
    "no_family": "Aucune connexion familiale.",
    "no_social": "Aucun cercle social ajoute.",
    "no_events": "Aucun evenement a venir dans les 3 prochains jours.",
    "initializing_projects": "Initialisation des projets...",
    "hardware": "Materiel",
    "hw_subtitle": "Capacites CPU & SIMD",
    "detecting_hw": "Detection du materiel...",
    "llm_benchmark": "Benchmark LLM",
    "bench_subtitle": "Debit & Evaluation des Performances",
    "bench_empty": "Cliquez sur un bouton de tier pour mesurer les tokens/seconde.",
    "bench_instant": "Bench instant",
    "bench_standard": "Bench standard",
    "bench_deep": "Bench deep",
    "bench_run_all": "Tout Lancer",
    "excellent": "Excellent",
    "good": "Bon",
    "moderate": "Modere",
    "slow": "Lent",
    "edit": "Modifier",
    "save_profile": "Enregistrer le Profil",
    "discard": "Annuler",
    "birthday": "Anniversaire",
    "gender": "Genre",
    "residency": "Residence",
    "town": "Ville",
    "country": "Pays",
    "timezone_label": "Fuseau Horaire",
    "briefing_time": "Heure du Briefing",
    "language_label": "Langue",
    "work_times": "Horaires de Travail",
    "life_goals": "Objectifs de Vie & Valeurs",
    "no_goals": "Aucun objectif defini.",
    "not_set": "Non defini",
}

_JA = {
    "project_name": "Operations",
    "board_name": "Operator Board",
    "list_today": "Today",
    "list_this_week": "This Week",
    "list_backlog": "Backlog",
    "list_done": "Done",
    "list_inbox": "Inbox",
    "life_overview": "Life Overview",
    "mapping_world": "Mapping your world...",
    "boards_heading": "Boards",
    "new_board": "+ New Board",
    "inner_circle": "Inner Circle",
    "inner_subtitle": "Family & Care",
    "close_circle": "Close Circle",
    "close_subtitle": "Friends & Social",
    "timeline_heading": "Timeline (Next 3 Days)",
    "no_family": "No family connections.",
    "no_social": "No social circle added.",
    "no_events": "No upcoming events for the next 3 days.",
    "initializing_projects": "Initializing projects...",
    "hardware": "Hardware",
    "hw_subtitle": "CPU & SIMD",
    "detecting_hw": "Detecting hardware...",
    "llm_benchmark": "LLM Benchmark",
    "bench_subtitle": "Throughput & Performance",
    "bench_empty": "Click a tier button to measure tokens/second.",
    "excellent": "Excellent",
    "good": "Good",
    "moderate": "Moderate",
    "slow": "Slow",
    "edit": "Edit",
    "save_profile": "Save Profile",
    "discard": "Discard",
    "birthday": "Birthday",
    "gender": "Gender",
    "residency": "Residency",
    "town": "Town",
    "country": "Country",
    "timezone_label": "Timezone",
    "briefing_time": "Briefing Time",
    "language_label": "Language",
    "work_times": "Work Times",
    "life_goals": "Life Goals & Core Values",
    "no_goals": "No goals set.",
    "not_set": "Not set",
}

# ── Registry ────────────────────────────────────────────────────────────
# Maps ISO 639-1 codes to their translation dict. Languages without a
# dedicated dict automatically fall back to English.

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": _EN,
    "de": _DE,
    "es": _ES,
    "fr": _FR,
    "ja": _JA,
}


def get_translations(lang_code: str = "en") -> dict[str, str]:
    """Return the full translation dict for a language, falling back to English
    for any missing keys."""
    base = _EN.copy()
    if lang_code != "en" and lang_code in _TRANSLATIONS:
        base.update(_TRANSLATIONS[lang_code])
    return base


def get_all_values(key: str) -> set[str]:
    """Return the set of all translated values for a given key across every
    registered language. Useful for matching Planka entity names regardless
    of which language they were created in."""
    values: set[str] = set()
    for lang_dict in _TRANSLATIONS.values():
        val = lang_dict.get(key)
        if val:
            values.add(val)
    # Always include English
    en_val = _EN.get(key)
    if en_val:
        values.add(en_val)
    return values


def get_planka_entity_names(lang_code: str = "en") -> dict[str, str]:
    """Convenience: return only the Planka-relevant entity names for a language."""
    t = get_translations(lang_code)
    return {
        "project_name": t["project_name"],
        "board_name": t["board_name"],
        "list_today": t["list_today"],
        "list_this_week": t["list_this_week"],
        "list_backlog": t["list_backlog"],
        "list_done": t["list_done"],
        "list_inbox": t["list_inbox"],
    }


def get_done_keywords() -> set[str]:
    """Return all translated variants of 'done' list names, plus common English
    synonyms, for use in progress-percentage calculations."""
    keywords: set[str] = set()
    for lang_dict in _TRANSLATIONS.values():
        done_val = lang_dict.get("list_done", "")
        if done_val:
            keywords.add(done_val.lower())
    # Add common English synonyms used in existing logic
    keywords.update({"done", "complete", "finish", "erledigt", "termine", "hecho"})
    return keywords
