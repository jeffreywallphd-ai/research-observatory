(() => {
  const root = document.documentElement;
  const body = document.body;
  const storage = {
    get(key) {
      try { return window.localStorage.getItem(key); } catch (_) { return null; }
    },
    set(key, value) {
      try { window.localStorage.setItem(key, value); } catch (_) { /* Non-persistent file or restricted context. */ }
    }
  };
  const storedTheme = storage.get('ro-theme');
  const preferredDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = storedTheme || (preferredDark ? 'dark' : 'light');

  const updateThemeLabels = () => {
    const dark = root.dataset.theme === 'dark';
    const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
    document.querySelectorAll('[data-theme-toggle]').forEach((el) => {
      el.setAttribute('aria-label', label);
      el.setAttribute('title', label);
    });
    document.querySelectorAll('[data-theme-icon]').forEach((el) => {
      el.innerHTML = dark
        ? '<svg class="icon"><use href="#icon-sun"></use></svg>'
        : '<svg class="icon"><use href="#icon-moon"></use></svg>';
    });
  };

  updateThemeLabels();
  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      storage.set('ro-theme', root.dataset.theme);
      updateThemeLabels();
    });
  });

  if (storage.get('ro-sidebar') === 'collapsed') {
    body.classList.add('sidebar-collapsed');
  }
  document.querySelectorAll('[data-sidebar-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      body.classList.toggle('sidebar-collapsed');
      storage.set('ro-sidebar', body.classList.contains('sidebar-collapsed') ? 'collapsed' : 'expanded');
    });
  });

  document.querySelectorAll('[data-tab-group]').forEach((group) => {
    const buttons = group.querySelectorAll('[data-tab]');
    const panels = group.querySelectorAll('[data-tab-panel]');
    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        buttons.forEach((b) => {
          b.classList.toggle('active', b === button);
          b.setAttribute('aria-selected', b === button ? 'true' : 'false');
        });
        panels.forEach((panel) => {
          panel.hidden = panel.dataset.tabPanel !== button.dataset.tab;
        });
      });
    });
  });

  document.querySelectorAll('[data-segmented]').forEach((group) => {
    group.querySelectorAll('button').forEach((button) => {
      button.addEventListener('click', () => {
        group.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === button));
      });
    });
  });

  document.querySelectorAll('[data-toast]').forEach((button) => {
    button.addEventListener('click', () => {
      const message = button.dataset.toast || 'Mock action recorded.';
      let toast = document.querySelector('.mock-toast');
      if (!toast) {
        toast = document.createElement('div');
        toast.className = 'mock-toast';
        toast.setAttribute('role', 'status');
        Object.assign(toast.style, {
          position: 'fixed', right: '24px', bottom: '24px', zIndex: '999',
          padding: '12px 16px', borderRadius: '10px', background: 'var(--text-strong)',
          color: 'var(--surface-1)', boxShadow: 'var(--shadow-lg)', fontSize: '13px',
          fontWeight: '700', opacity: '0', transform: 'translateY(8px)', transition: 'all 160ms ease'
        });
        document.body.appendChild(toast);
      }
      toast.textContent = message;
      requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
      });
      window.clearTimeout(window.__roToastTimer);
      window.__roToastTimer = window.setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
      }, 2200);
    });
  });

  document.querySelectorAll('[data-filter]').forEach((button) => {
    button.addEventListener('click', () => button.classList.toggle('active'));
  });


  const WORKFLOW_PROFILES = {
  "rapid-orientation": {
    "title": "Rapid field orientation",
    "purpose": "Establish vocabulary, seminal work, schools, and current debates without claiming systematic completeness.",
    "output": "Field map, reading path, and contested claims",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Research Intent",
        "Define orientation scope and vocabulary needs.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Develop vocabulary and discover seminal and adjacent work.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Canvas",
        "Inspect schools, clusters, and discovery paths.",
        "grid"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Document Reader",
        "Read representative and contested sources.",
        "book"
      ],
      [
        "theory-map",
        "theory-map.html",
        "Theory Map",
        "Compare concepts, theories, and construct history.",
        "layers"
      ],
      [
        "claim-graph",
        "claim-graph.html",
        "Claim Graph",
        "Identify central and disputed claims.",
        "network"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Orientation Synthesis",
        "Produce a bounded field map and reading path.",
        "pen"
      ]
    ]
  },
  "systematic-review": {
    "title": "Systematic / scoping review",
    "purpose": "Construct and report a reproducible evidence corpus.",
    "output": "Protocol, corpus, evidence table, cited synthesis, and audit bundle",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Protocol & Intent",
        "Define question, inclusion logic, sources, and stopping.",
        "document"
      ],
      [
        "source-manager",
        "source-manager.html",
        "Source Manager",
        "Configure databases, rights, and adapters.",
        "database"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Run and version reproducible source-specific searches.",
        "search"
      ],
      [
        "ingestion-reconciliation",
        "ingestion-reconciliation.html",
        "Ingestion Review",
        "Reconcile versions, duplicates, corrections, and rights.",
        "refresh"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Diagnostics",
        "Audit coverage, missingness, and discovery paths.",
        "grid"
      ],
      [
        "screening",
        "screening.html",
        "Screening",
        "Apply human inclusion authority with audits and stopping.",
        "clipboard"
      ],
      [
        "parsing-quality",
        "parsing-quality.html",
        "Parsing Quality",
        "Verify full-text structure and stable source anchors.",
        "check"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Evidence Matrix",
        "Extract, verify, compare, and adjudicate evidence.",
        "table"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Synthesis Studio",
        "Produce cited synthesis and reporting outputs.",
        "pen"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Audit & Lineage",
        "Export the reproducibility and disclosure bundle.",
        "history"
      ]
    ]
  },
  "living-review": {
    "title": "Living review",
    "purpose": "Maintain an existing synthesis as evidence and corrections arrive.",
    "output": "Change report, updated synthesis, and affected-claim alerts",
    "cyclical": true,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Update Contract",
        "Confirm update scope, cadence, and decision rules.",
        "document"
      ],
      [
        "living-monitor",
        "living-monitor.html",
        "Living Monitor",
        "Triage new work and affected prior conclusions.",
        "pulse"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Differential Search",
        "Run saved and expanded update searches.",
        "search"
      ],
      [
        "ingestion-reconciliation",
        "ingestion-reconciliation.html",
        "Ingestion Review",
        "Reconcile new versions, corrections, and duplicates.",
        "refresh"
      ],
      [
        "screening",
        "screening.html",
        "Differential Screening",
        "Screen only new and changed records with audits.",
        "clipboard"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Evidence Update",
        "Extract and verify changed evidence.",
        "table"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Update Synthesis",
        "Revise only affected claims and narratives.",
        "pen"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Change Audit",
        "Publish change, staleness, and decision history.",
        "history"
      ]
    ]
  },
  "theory-synthesis": {
    "title": "Theory synthesis",
    "purpose": "Clarify and integrate constructs, mechanisms, theory use, relationships, and boundaries.",
    "output": "Theory architecture, construct map, mechanisms, and integration opportunities",
    "cyclical": false,
    "defaultIndex": 5,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Research Intent",
        "Define theoretical objective, unit, scope, and contribution.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Discover theoretical traditions and terminology.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Canvas",
        "Map clusters, lineages, and fragmentation.",
        "grid"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Document Reader",
        "Read theory use and construct definitions in context.",
        "book"
      ],
      [
        "schema-manager",
        "schema-manager.html",
        "Schema Manager",
        "Define theory, construct, mechanism, level, and boundary fields.",
        "sliders"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Evidence Matrix",
        "Normalize and verify comparable theoretical evidence.",
        "table"
      ],
      [
        "theory-map",
        "theory-map.html",
        "Theory Map",
        "Integrate definitions, mechanisms, operationalizations, and drift.",
        "layers"
      ],
      [
        "claim-graph",
        "claim-graph.html",
        "Claim Graph",
        "Connect propositions, findings, qualifications, and disputes.",
        "network"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Integration Opportunities",
        "Assess boundary, contradiction, bridge, and integration candidates.",
        "target"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Synthesis Studio",
        "Produce the theory architecture and evidence-linked narrative.",
        "pen"
      ]
    ]
  },
  "hermeneutic-inquiry": {
    "title": "Hermeneutic inquiry",
    "purpose": "Deepen understanding through iterative search-read-interpret-memo cycles.",
    "output": "Interpretive map, evolving questions, and rationale trail",
    "cyclical": true,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Initial Horizon",
        "Declare the provisional question and interpretive stance.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search",
        "Find texts that expand or challenge current understanding.",
        "search"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Read",
        "Inspect sources closely in their original context.",
        "book"
      ],
      [
        "research-notebook",
        "research-notebook.html",
        "Interpret & Memo",
        "Record human interpretations, questions, and alternatives.",
        "pen"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Reframe Corpus",
        "Revise vocabulary, boundaries, and reading sets.",
        "grid"
      ],
      [
        "theory-map",
        "theory-map.html",
        "Interpretive Map",
        "Trace concepts, histories, and relationships.",
        "layers"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Interpretive Synthesis",
        "Present understanding and its documented evolution.",
        "pen"
      ]
    ]
  },
  "critical-problematization": {
    "title": "Critical problematization",
    "purpose": "Surface and challenge assumptions, exclusions, authority arrangements, and foreclosed alternatives.",
    "output": "Problematization dossier and competing framings",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Critical Intent",
        "Declare object, standpoint, stakeholders, and authority limits.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Retrieve dominant, marginal, historical, and adjacent framings.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Reflexivity",
        "Inspect whose work, languages, settings, and methods dominate.",
        "grid"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Close Reading",
        "Read problem formulations, boundaries, and normative language.",
        "book"
      ],
      [
        "research-notebook",
        "research-notebook.html",
        "Critical Memos",
        "Develop and preserve alternative readings.",
        "pen"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Critical Coding",
        "Code assumptions, stakeholders, authority, benefits, burdens, and absences.",
        "table"
      ],
      [
        "critical-lens",
        "critical-lens.html",
        "Critical Lens",
        "Compare assumptions and excluded alternatives.",
        "eye"
      ],
      [
        "claim-graph",
        "claim-graph.html",
        "Argument Structure",
        "Trace how claims depend on assumptions and boundaries.",
        "network"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Problematization Opportunities",
        "Assess assumption-challenging and silence candidates.",
        "target"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Problematization Dossier",
        "Present evidence, counter-readings, and researcher adjudication.",
        "pen"
      ]
    ]
  },
  "technical-landscape": {
    "title": "Technical landscape / benchmark audit",
    "purpose": "Audit methods, baselines, datasets, compute, controls, and evaluation quality.",
    "output": "Benchmark map, missing controls, and study-design opportunities",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Audit Contract",
        "Define systems, tasks, compute, baselines, and validity criteria.",
        "document"
      ],
      [
        "source-manager",
        "source-manager.html",
        "Source Manager",
        "Configure papers, repositories, datasets, and reports.",
        "database"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Discover methods, benchmark families, and adjacent terms.",
        "search"
      ],
      [
        "ingestion-reconciliation",
        "ingestion-reconciliation.html",
        "Artifact Reconciliation",
        "Link versions, code, data, corrections, and canonical studies.",
        "refresh"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Landscape Map",
        "Map method, model, dataset, and benchmark clusters.",
        "grid"
      ],
      [
        "screening",
        "screening.html",
        "Comparability Screening",
        "Apply scope and minimum reporting criteria.",
        "clipboard"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Benchmark Evidence",
        "Compare models, data, compute, baselines, controls, and results.",
        "table"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Study-design Opportunities",
        "Identify missing controls, ablations, replications, and external validation.",
        "target"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Technical Synthesis",
        "Produce the benchmark audit and design recommendations.",
        "pen"
      ]
    ]
  },
  "novelty-audit": {
    "title": "Novelty & research-opportunity audit",
    "purpose": "Test a proposed contribution against the closest prior work.",
    "output": "Bounded novelty statement and opportunity dossier",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Candidate & Standard",
        "Define contribution, facets, scope, and novelty standard.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Adversarial Search",
        "Search alternate terms, histories, disciplines, and source types.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Nearest Landscape",
        "Map semantic and citation neighbors.",
        "grid"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Comparison Evidence",
        "Compare contexts, constructs, methods, and claims.",
        "table"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Opportunity Candidate",
        "Type and rank the opportunity with counterevidence.",
        "target"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Novelty Challenge",
        "Rank threatening prior work and adjudicate a bounded disposition.",
        "shield"
      ],
      [
        "synthesis-studio",
        "synthesis-studio.html",
        "Export Dossier",
        "Produce the bounded statement and audit manifest.",
        "pen"
      ]
    ]
  },
  "empirical-study-design": {
    "title": "Empirical study design",
    "purpose": "Turn a corroborated research opportunity and literature evidence into an ethical, feasible, reproducible empirical design.",
    "output": "Study-design dossier, protocol skeleton, validity and ethics review, and analysis plan",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Study Intent",
        "Define phenomenon, contribution, population, constraints, and decision authority.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Evidence Search",
        "Find theory, measures, methods, datasets, and comparable designs.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Design Landscape",
        "Map study families, contexts, methods, and measurement traditions.",
        "grid"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Design Evidence",
        "Compare constructs, measures, samples, methods, effects, and validity threats.",
        "table"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Research Opportunity",
        "Select a theoretically meaningful and tractable opportunity.",
        "target"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Novelty Challenge",
        "Test contribution facets and nearest prior designs.",
        "shield"
      ],
      [
        "study-design",
        "study-design.html",
        "Study Design Studio",
        "Compare alternatives and formalize sampling, measurement, procedure, analysis, ethics, and reproducibility.",
        "flask"
      ],
      [
        "manuscript-blueprint",
        "manuscript-blueprint.html",
        "Protocol Blueprint",
        "Create a protocol or registered-report skeleton and evidence plan.",
        "blueprint"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Design Audit",
        "Export assumptions, evidence, decisions, and reproducibility records.",
        "history"
      ]
    ]
  },
  "empirical-study-to-article": {
    "title": "Empirical study to article",
    "purpose": "Move from literature-grounded opportunity through study design and verified study results to an article and adversarial review.",
    "output": "Study protocol, verified result package, full empirical manuscript, simulated reviews, revision, and audit bundle",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Research Intent",
        "Define empirical contribution, constraints, outputs, and authority.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Literature Search",
        "Build the theoretical, methodological, and measurement evidence base.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Map",
        "Inspect field structure, prior designs, and coverage.",
        "grid"
      ],
      [
        "screening",
        "screening.html",
        "Evidence Screening",
        "Create the bounded set supporting theory, method, and interpretation.",
        "clipboard"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Evidence Matrix",
        "Verify constructs, measures, designs, results, and boundary conditions.",
        "table"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Opportunity",
        "Choose a consequential and tractable research opportunity.",
        "target"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Novelty Challenge",
        "Bound contribution against nearest prior work.",
        "shield"
      ],
      [
        "study-design",
        "study-design.html",
        "Study Design Studio",
        "Finalize questions, hypotheses, sampling, measures, procedure, analysis, ethics, and preregistration.",
        "flask"
      ],
      [
        "manuscript-blueprint",
        "manuscript-blueprint.html",
        "Article Blueprint",
        "Plan venue, sections, claims, evidence, word budgets, tables, and figures.",
        "blueprint"
      ],
      [
        "technical-reports",
        "technical-reports.html",
        "Technical Reports & Results",
        "Upload reports and verify methods, results, deviations, tables, figures, and limitations.",
        "upload"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Manuscript Studio",
        "Draft the empirical article from approved literature, blueprint, and verified results.",
        "edit"
      ],
      [
        "reviewer-simulation",
        "reviewer-simulation.html",
        "Reviewer Simulation",
        "Run independent methodological, theoretical, editorial, and omitted-literature review.",
        "review"
      ],
      [
        "revision-response",
        "revision-response.html",
        "Revision & Response",
        "Adjudicate issues, revise the manuscript, and draft linked responses.",
        "comments"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Publication Audit",
        "Export source, result, authorship, model, review, and revision lineage.",
        "history"
      ]
    ]
  },
  "empirical-results-to-article": {
    "title": "Empirical results to article",
    "purpose": "Begin from completed empirical work and technical reports, reconstruct the evidence context, and produce a source-grounded article.",
    "output": "Verified result package, literature-grounded empirical manuscript, simulated review, revision, and audit bundle",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Article Intent",
        "Declare study, contribution, report set, target output, and boundaries.",
        "document"
      ],
      [
        "technical-reports",
        "technical-reports.html",
        "Technical Reports & Results",
        "Upload and reconcile reports, outputs, methods, results, deviations, and limitations.",
        "upload"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Context Search",
        "Retrieve theory, methods, measures, and nearest prior results.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Prior-work Landscape",
        "Map the study against the field and nearest designs.",
        "grid"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Integrated Evidence",
        "Verify literature and report-derived evidence in comparable form.",
        "table"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Contribution Audit",
        "Test the actual study contribution against prior work.",
        "shield"
      ],
      [
        "manuscript-blueprint",
        "manuscript-blueprint.html",
        "Article Blueprint",
        "Plan research-type and venue-specific structure, claims, tables, and figures.",
        "blueprint"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Manuscript Studio",
        "Draft the article from accepted evidence and verified results.",
        "edit"
      ],
      [
        "reviewer-simulation",
        "reviewer-simulation.html",
        "Reviewer Simulation",
        "Challenge methods, interpretation, contribution, reporting, and omitted literature.",
        "review"
      ],
      [
        "revision-response",
        "revision-response.html",
        "Revision & Response",
        "Revise and record author dispositions and responses.",
        "comments"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Publication Audit",
        "Export complete evidence and drafting lineage.",
        "history"
      ]
    ]
  },
  "theory-article-development": {
    "title": "Theory article development",
    "purpose": "Develop a theory paper from evidence-linked integration, problem framing, and bounded contribution through full manuscript and review.",
    "output": "Theory architecture, article blueprint, full theory manuscript, simulated reviews, revision, and audit bundle",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Theory Article Intent",
        "Define phenomenon, contribution logic, audience, and article type.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Search Studio",
        "Discover traditions, concepts, mechanisms, and adjacent literatures.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Field Architecture",
        "Map schools, lineages, fragmentation, and bridges.",
        "grid"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Close Reading",
        "Inspect definitions, mechanisms, arguments, and boundary claims.",
        "book"
      ],
      [
        "schema-manager",
        "schema-manager.html",
        "Theory Schema",
        "Define constructs, mechanisms, levels, propositions, and boundaries.",
        "sliders"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Theory Evidence",
        "Verify comparable definitions, uses, findings, and qualifications.",
        "table"
      ],
      [
        "theory-map",
        "theory-map.html",
        "Theory Map",
        "Develop the integrated conceptual architecture.",
        "layers"
      ],
      [
        "claim-graph",
        "claim-graph.html",
        "Argument Graph",
        "Build claims, warrants, counterarguments, and proposition logic.",
        "network"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Theory Opportunity",
        "Select integration, contradiction, boundary, or mechanism contribution.",
        "target"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Novelty Challenge",
        "Test the theory contribution against nearest prior architectures.",
        "shield"
      ],
      [
        "manuscript-blueprint",
        "manuscript-blueprint.html",
        "Theory Blueprint",
        "Create article skeleton, section purposes, claim plan, and exhibit plan.",
        "blueprint"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Manuscript Studio",
        "Draft the theory article from approved claims and evidence.",
        "edit"
      ],
      [
        "reviewer-simulation",
        "reviewer-simulation.html",
        "Reviewer Simulation",
        "Run theory, contribution, logic, literature, and editorial reviews independently.",
        "review"
      ],
      [
        "revision-response",
        "revision-response.html",
        "Revision & Response",
        "Revise argument and record dispositions and responses.",
        "comments"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Publication Audit",
        "Export evidence, authorship, drafting, and review lineage.",
        "history"
      ]
    ]
  },
  "critical-article-development": {
    "title": "Critical article development",
    "purpose": "Develop an evidence-grounded critical article that challenges assumptions, power relations, exclusions, or dominant problem formulations.",
    "output": "Problematization architecture, critical article blueprint, full manuscript, simulated reviews, revision, and audit bundle",
    "cyclical": false,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Critical Article Intent",
        "Declare object, standpoint, stakes, audience, and interpretive authority.",
        "document"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Plural Search",
        "Retrieve dominant, marginal, historical, and adjacent framings.",
        "search"
      ],
      [
        "corpus-canvas",
        "corpus-canvas.html",
        "Corpus Reflexivity",
        "Inspect representation, hierarchy, language, and coverage.",
        "grid"
      ],
      [
        "document-reader",
        "document-reader.html",
        "Close Reading",
        "Read framing, system boundaries, agency, and normative commitments.",
        "book"
      ],
      [
        "research-notebook",
        "research-notebook.html",
        "Critical Memos",
        "Develop alternative readings and preserve interpretive evolution.",
        "pen"
      ],
      [
        "evidence-matrix",
        "evidence-matrix.html",
        "Critical Evidence",
        "Code assumptions, authority, dependency, stakeholders, benefits, burdens, and silences.",
        "table"
      ],
      [
        "critical-lens",
        "critical-lens.html",
        "Critical Lens",
        "Develop contestable problematization and alternative framings.",
        "eye"
      ],
      [
        "claim-graph",
        "claim-graph.html",
        "Argument Graph",
        "Trace claims, warrants, assumptions, rebuttals, and exclusions.",
        "network"
      ],
      [
        "opportunity-radar",
        "opportunity-radar.html",
        "Critical Contribution",
        "Assess assumption challenge, silence, reframing, and integration opportunities.",
        "target"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Novelty Challenge",
        "Test the framing against prior critical and adjacent work.",
        "shield"
      ],
      [
        "manuscript-blueprint",
        "manuscript-blueprint.html",
        "Critical Blueprint",
        "Create article skeleton, argumentative movement, evidence plan, and reflexivity requirements.",
        "blueprint"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Manuscript Studio",
        "Draft the critical article while preserving evidence and interpretive authorship.",
        "edit"
      ],
      [
        "reviewer-simulation",
        "reviewer-simulation.html",
        "Reviewer Simulation",
        "Run critical, theory, evidence, reflexivity, counter-position, and editorial reviews.",
        "review"
      ],
      [
        "revision-response",
        "revision-response.html",
        "Revision & Response",
        "Adjudicate critiques, revise framing, and record responses.",
        "comments"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Publication Audit",
        "Export evidence, interpretation, authorship, and review lineage.",
        "history"
      ]
    ]
  },
  "manuscript-review-revision": {
    "title": "Manuscript review & revision",
    "purpose": "Challenge an uploaded or generated article draft, locate omitted evidence, synthesize independent reviews, and govern revision.",
    "output": "Review package, editorial synthesis, revision plan, revised manuscript, response document, and audit bundle",
    "cyclical": true,
    "steps": [
      [
        "intent-contract",
        "intent-contract.html",
        "Review Contract",
        "Declare article type, target venue, review roles, confidentiality, and decision authority.",
        "document"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Draft Intake",
        "Upload or open a draft and map sections, claims, citations, tables, and figures.",
        "edit"
      ],
      [
        "search-studio",
        "search-studio.html",
        "Omitted-literature Search",
        "Search for missing, contradictory, and threatening prior work.",
        "search"
      ],
      [
        "novelty-audit",
        "novelty-audit.html",
        "Contribution Challenge",
        "Test novelty and positioning against nearest prior work.",
        "shield"
      ],
      [
        "reviewer-simulation",
        "reviewer-simulation.html",
        "Independent Reviews",
        "Run role-separated methodological, theoretical, critical, reporting, and editorial reviews.",
        "review"
      ],
      [
        "revision-response",
        "revision-response.html",
        "Revision & Response",
        "Triage issues, record dispositions, revise, and draft responses.",
        "comments"
      ],
      [
        "manuscript-studio",
        "manuscript-studio.html",
        "Revised Manuscript",
        "Review the integrated revised article and unresolved claims.",
        "edit"
      ],
      [
        "audit-lineage",
        "audit-lineage.html",
        "Review Audit",
        "Export review prompts, evidence, decisions, revisions, and disclosure.",
        "history"
      ]
    ]
  }
};

  const workflowKey = storage.get('ro-workflow') || 'empirical-study-to-article';
  let activeWorkflowKey = WORKFLOW_PROFILES[workflowKey] ? workflowKey : 'empirical-study-to-article';
  const currentPage = body.dataset.page;
  const iconSvg = (name) => `<svg class="icon" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;

  const renderWorkflow = () => {
    const profile = WORKFLOW_PROFILES[activeWorkflowKey];
    const pageIndex = profile.steps.findIndex((step) => step[0] === currentPage);
    const storedIndex = Number(storage.get(`ro-workflow-index-${activeWorkflowKey}`));
    const activeIndex = pageIndex >= 0 ? pageIndex : (Number.isFinite(storedIndex) && storedIndex >= 0 ? Math.min(storedIndex, profile.steps.length - 1) : (profile.defaultIndex || 0));
    if (pageIndex >= 0) storage.set(`ro-workflow-index-${activeWorkflowKey}`, String(pageIndex));

    document.querySelectorAll('[data-workflow-select]').forEach((select) => { select.value = activeWorkflowKey; });
    document.querySelectorAll('[data-current-workflow-title]').forEach((el) => { el.textContent = profile.title; });
    document.querySelectorAll('[data-workflow-progress-label]').forEach((el) => { el.textContent = `Step ${activeIndex + 1} of ${profile.steps.length}${profile.cyclical ? ' · cyclical' : ''}`; });
    document.querySelectorAll('[data-workflow-progress]').forEach((el) => { el.style.setProperty('--value', `${Math.round(((activeIndex + 1) / profile.steps.length) * 100)}%`); });

    document.querySelectorAll('[data-workflow-nav]').forEach((nav) => {
      nav.innerHTML = profile.steps.map((step, index) => {
        const [key, href, label, rationale, icon] = step;
        const state = index < activeIndex ? 'complete' : index === activeIndex ? 'current' : '';
        const current = key === currentPage ? ' aria-current="step"' : '';
        return `<a class="workflow-nav-step ${state}" href="${href}"${current} title="${rationale}"><span class="workflow-step-marker">${index < activeIndex ? '✓' : index + 1}</span><span class="workflow-step-copy"><span class="workflow-step-name">${label}</span><span class="workflow-step-meta">${index === activeIndex ? 'Current step' : index < activeIndex ? 'Completed' : 'Upcoming'}</span></span>${iconSvg(icon)}</a>`;
      }).join('');
    });

    document.querySelectorAll('[data-workflow-context]').forEach((context) => {
      if (currentPage === 'project-home' || currentPage === 'projects' || currentPage === 'new-project' || currentPage === 'intent-contract' || currentPage === 'prototype-index' || currentPage === 'style-guide') {
        context.hidden = true;
        return;
      }
      context.hidden = false;
      if (pageIndex >= 0) {
        const step = profile.steps[pageIndex];
        const prev = pageIndex > 0 ? profile.steps[pageIndex - 1] : null;
        const next = pageIndex < profile.steps.length - 1 ? profile.steps[pageIndex + 1] : null;
        context.classList.remove('supporting');
        context.innerHTML = `<div class="workflow-context-main"><span class="badge badge-brand">${profile.title}</span><strong>Step ${pageIndex + 1} of ${profile.steps.length} · ${step[2]}</strong><span class="small muted">${step[3]}</span></div><div class="workflow-context-actions">${prev ? `<a class="btn" href="${prev[1]}">← ${prev[2]}</a>` : ''}${next ? `<a class="btn btn-primary" href="${next[1]}">Next: ${next[2]} →</a>` : `<a class="btn btn-primary" href="index.html">Review project home →</a>`}</div>`;
      } else {
        const current = profile.steps[activeIndex];
        context.classList.add('supporting');
        context.innerHTML = `<div class="workflow-context-main"><span class="badge badge-info">Supporting tool</span><strong>Outside the primary sequence</strong><span class="small muted">This tool remains available, but the current ${profile.title} step is ${current[2]}.</span></div><div class="workflow-context-actions"><a class="btn btn-primary" href="${current[1]}">Return to ${current[2]} →</a><a class="btn" href="intent-contract.html">Edit workflow</a></div>`;
      }
    });

    document.querySelectorAll('[data-workflow-map]').forEach((map) => {
      map.innerHTML = profile.steps.map((step, index) => `<a class="workflow-map-step ${index < activeIndex ? 'complete' : index === activeIndex ? 'current' : ''}" href="${step[1]}" title="${step[3]}"><span>${index < activeIndex ? '✓' : index + 1}</span><small>${step[2]}</small></a>`).join('');
    });
    const nextStep = profile.steps[Math.min(activeIndex + 1, profile.steps.length - 1)];
    document.querySelectorAll('[data-workflow-next-title]').forEach((el) => { el.textContent = nextStep[2]; });
    document.querySelectorAll('[data-workflow-next-description]').forEach((el) => { el.textContent = nextStep[3]; });
    document.querySelectorAll('[data-workflow-next-link]').forEach((el) => { el.href = nextStep[1]; });

    document.querySelectorAll('[data-workflow-card]').forEach((card) => {
      const input = card.querySelector('[data-workflow-choice]');
      card.classList.toggle('selected', Boolean(input && input.value === activeWorkflowKey));
    });
  };

  document.querySelectorAll('[data-workflow-select]').forEach((select) => {
    select.addEventListener('change', () => {
      if (WORKFLOW_PROFILES[select.value]) {
        activeWorkflowKey = select.value;
        storage.set('ro-workflow', activeWorkflowKey);
        renderWorkflow();
      }
    });
  });
  document.querySelectorAll('[data-workflow-choice]').forEach((input) => {
    input.addEventListener('change', () => {
      if (input.checked && WORKFLOW_PROFILES[input.value]) {
        activeWorkflowKey = input.value;
        storage.set('ro-workflow', activeWorkflowKey);
        renderWorkflow();
      }
    });
  });
  renderWorkflow();

})();
