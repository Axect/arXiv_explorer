"""Static arXiv category taxonomy."""

ARXIV_CATEGORIES: dict[str, dict[str, str]] = {
    "Physics": {
        "astro-ph": "Astrophysics",
        "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
        "astro-ph.EP": "Earth and Planetary Astrophysics",
        "astro-ph.GA": "Astrophysics of Galaxies",
        "astro-ph.HE": "High Energy Astrophysical Phenomena",
        "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
        "astro-ph.SR": "Solar and Stellar Astrophysics",
        "cond-mat": "Condensed Matter",
        "cond-mat.dis-nn": "Disordered Systems and Neural Networks",
        "cond-mat.mes-hall": "Mesoscale and Nanoscale Physics",
        "cond-mat.mtrl-sci": "Materials Science",
        "cond-mat.other": "Other Condensed Matter",
        "cond-mat.quant-gas": "Quantum Gases",
        "cond-mat.soft": "Soft Condensed Matter",
        "cond-mat.stat-mech": "Statistical Mechanics",
        "cond-mat.str-el": "Strongly Correlated Electrons",
        "cond-mat.supr-con": "Superconductivity",
        "gr-qc": "General Relativity and Quantum Cosmology",
        "hep-ex": "High Energy Physics - Experiment",
        "hep-lat": "High Energy Physics - Lattice",
        "hep-ph": "High Energy Physics - Phenomenology",
        "hep-th": "High Energy Physics - Theory",
        "math-ph": "Mathematical Physics",
        "nlin.AO": "Adaptation and Self-Organizing Systems",
        "nlin.CD": "Chaotic Dynamics",
        "nlin.CG": "Cellular Automata and Lattice Gases",
        "nlin.PS": "Pattern Formation and Solitons",
        "nlin.SI": "Exactly Solvable and Integrable Systems",
        "nucl-ex": "Nuclear Experiment",
        "nucl-th": "Nuclear Theory",
        "physics.acc-ph": "Accelerator Physics",
        "physics.ao-ph": "Atmospheric and Oceanic Physics",
        "physics.app-ph": "Applied Physics",
        "physics.atm-clus": "Atomic and Molecular Clusters",
        "physics.atom-ph": "Atomic Physics",
        "physics.bio-ph": "Biological Physics",
        "physics.chem-ph": "Chemical Physics",
        "physics.class-ph": "Classical Physics",
        "physics.comp-ph": "Computational Physics",
        "physics.data-an": "Data Analysis, Statistics and Probability",
        "physics.ed-ph": "Physics Education",
        "physics.flu-dyn": "Fluid Dynamics",
        "physics.gen-ph": "General Physics",
        "physics.geo-ph": "Geophysics",
        "physics.hist-ph": "History and Philosophy of Physics",
        "physics.ins-det": "Instrumentation and Detectors",
        "physics.med-ph": "Medical Physics",
        "physics.optics": "Optics",
        "physics.plasm-ph": "Plasma Physics",
        "physics.pop-ph": "Popular Physics",
        "physics.soc-ph": "Physics and Society",
        "physics.space-ph": "Space Physics",
        "quant-ph": "Quantum Physics",
    },
    "Computer Science": {
        "cs.AI": "Artificial Intelligence",
        "cs.AR": "Hardware Architecture",
        "cs.CC": "Computational Complexity",
        "cs.CE": "Computational Engineering, Finance, and Science",
        "cs.CG": "Computational Geometry",
        "cs.CL": "Computation and Language",
        "cs.CR": "Cryptography and Security",
        "cs.CV": "Computer Vision and Pattern Recognition",
        "cs.CY": "Computers and Society",
        "cs.DB": "Databases",
        "cs.DC": "Distributed, Parallel, and Cluster Computing",
        "cs.DL": "Digital Libraries",
        "cs.DM": "Discrete Mathematics",
        "cs.DS": "Data Structures and Algorithms",
        "cs.ET": "Emerging Technologies",
        "cs.FL": "Formal Languages and Automata Theory",
        "cs.GL": "General Literature",
        "cs.GR": "Graphics",
        "cs.GT": "Computer Science and Game Theory",
        "cs.HC": "Human-Computer Interaction",
        "cs.IR": "Information Retrieval",
        "cs.IT": "Information Theory",
        "cs.LG": "Machine Learning",
        "cs.LO": "Logic in Computer Science",
        "cs.MA": "Multiagent Systems",
        "cs.MM": "Multimedia",
        "cs.MS": "Mathematical Software",
        "cs.NA": "Numerical Analysis",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.NI": "Networking and Internet Architecture",
        "cs.OH": "Other Computer Science",
        "cs.OS": "Operating Systems",
        "cs.PF": "Performance",
        "cs.PL": "Programming Languages",
        "cs.RO": "Robotics",
        "cs.SC": "Symbolic Computation",
        "cs.SD": "Sound",
        "cs.SE": "Software Engineering",
        "cs.SI": "Social and Information Networks",
        "cs.SY": "Systems and Control",
    },
    "Mathematics": {
        "math.AC": "Commutative Algebra",
        "math.AG": "Algebraic Geometry",
        "math.AP": "Analysis of PDEs",
        "math.AT": "Algebraic Topology",
        "math.CA": "Classical Analysis and ODEs",
        "math.CO": "Combinatorics",
        "math.CT": "Category Theory",
        "math.CV": "Complex Variables",
        "math.DG": "Differential Geometry",
        "math.DS": "Dynamical Systems",
        "math.FA": "Functional Analysis",
        "math.GM": "General Mathematics",
        "math.GN": "General Topology",
        "math.GR": "Group Theory",
        "math.GT": "Geometric Topology",
        "math.HO": "History and Overview",
        "math.IT": "Information Theory",
        "math.KT": "K-Theory and Homology",
        "math.LO": "Logic",
        "math.MG": "Metric Geometry",
        "math.MP": "Mathematical Physics",
        "math.NA": "Numerical Analysis",
        "math.NT": "Number Theory",
        "math.OA": "Operator Algebras",
        "math.OC": "Optimization and Control",
        "math.PR": "Probability",
        "math.QA": "Quantum Algebra",
        "math.RA": "Rings and Algebras",
        "math.RT": "Representation Theory",
        "math.SG": "Symplectic Geometry",
        "math.SP": "Spectral Theory",
        "math.ST": "Statistics Theory",
    },
    "Statistics": {
        "stat.AP": "Applications",
        "stat.CO": "Computation",
        "stat.ME": "Methodology",
        "stat.ML": "Machine Learning",
        "stat.OT": "Other Statistics",
        "stat.TH": "Statistics Theory",
    },
    "Quantitative Biology": {
        "q-bio.BM": "Biomolecules",
        "q-bio.CB": "Cell Behavior",
        "q-bio.GN": "Genomics",
        "q-bio.MN": "Molecular Networks",
        "q-bio.NC": "Neurons and Cognition",
        "q-bio.OT": "Other Quantitative Biology",
        "q-bio.PE": "Populations and Evolution",
        "q-bio.QM": "Quantitative Methods",
        "q-bio.SC": "Subcellular Processes",
        "q-bio.TO": "Tissues and Organs",
    },
    "Quantitative Finance": {
        "q-fin.CP": "Computational Finance",
        "q-fin.EC": "Economics",
        "q-fin.GN": "General Finance",
        "q-fin.MF": "Mathematical Finance",
        "q-fin.PM": "Portfolio Management",
        "q-fin.PR": "Pricing of Securities",
        "q-fin.RM": "Risk Management",
        "q-fin.ST": "Statistical Finance",
        "q-fin.TR": "Trading and Market Microstructure",
    },
    "Electrical Engineering and Systems Science": {
        "eess.AS": "Audio and Speech Processing",
        "eess.IV": "Image and Video Processing",
        "eess.SP": "Signal Processing",
        "eess.SY": "Systems and Control",
    },
    "Economics": {
        "econ.EM": "Econometrics",
        "econ.GN": "General Economics",
        "econ.TH": "Theoretical Economics",
    },
}


def get_all_categories() -> list[tuple[str, str, str]]:
    """Return flat list of (code, full_name, group) for all categories."""
    result = []
    for group, cats in ARXIV_CATEGORIES.items():
        for code, name in cats.items():
            result.append((code, name, group))
    return result


def fuzzy_search(query: str) -> list[tuple[str, str, str]]:
    """Fuzzy search categories. Returns list of (code, name, group) sorted by relevance."""
    if not query:
        return get_all_categories()
    query_lower = query.lower().strip()
    scored: list[tuple[float, str, str, str]] = []
    for code, name, group in get_all_categories():
        score = _fuzzy_score(query_lower, code.lower(), name.lower())
        if score > 0:
            scored.append((score, code, name, group))
    scored.sort(key=lambda x: -x[0])
    return [(code, name, group) for _, code, name, group in scored]


def _fuzzy_score(query: str, code: str, name: str) -> float:
    best = 0.0
    if query == code:
        return 100.0
    if code.startswith(query):
        best = max(best, 80.0 + len(query))
    if query == name:
        return 95.0
    if name.startswith(query):
        best = max(best, 70.0 + len(query))
    if query in code:
        best = max(best, 60.0 + len(query))
    if query in name:
        best = max(best, 50.0 + len(query))
    query_tokens = query.split()
    if query_tokens and all(t in name for t in query_tokens):
        best = max(best, 40.0 + len(query))
    seq_score = _char_sequence_score(query, code + " " + name)
    if seq_score > 0.5:
        best = max(best, 20.0 * seq_score)
    return best


def _char_sequence_score(query: str, target: str) -> float:
    if not query:
        return 0.0
    target_idx = 0
    matched = 0
    for ch in query:
        while target_idx < len(target):
            if target[target_idx] == ch:
                matched += 1
                target_idx += 1
                break
            target_idx += 1
    return matched / len(query)
