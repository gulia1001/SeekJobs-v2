# SeekJobs — how it works

GitHub draws the diagrams below automatically (Mermaid).

## 1. The whole system

```mermaid
flowchart LR
    subgraph Sources["Job sources (public)"]
        TG["Telegram IT channels<br/>devkz_jobs · itvacancykz · workitkz<br/>itcom_kz · zhumysbarit · halyk_jumys · insferaforyou"]
    end

    subgraph ETL["Daily ETL — Airflow, 08:00 Almaty"]
        E["Extract<br/>one task per channel"] --> T["Transform + Load<br/>vacancy filter + rules"]
        T --> X["Expire old jobs"] --> Q["Quality check"]
    end

    subgraph DB["Postgres"]
        RAW[("raw_posts<br/>every post, as written")]
        JOBS[("jobs<br/>structured vacancies")]
    end

    subgraph App["SeekJobs app"]
        API["FastAPI backend<br/>matching · CV generation · PDF/Word export"]
        WEB["Next.js website"]
    end

    USER(["Job seeker"])
    LLM["Groq LLM<br/>(optional)"]
    GH["GitHub API"]
    ALERT["Telegram alert<br/>to the team"]

    TG -- "t.me/s web preview" --> E
    E --> RAW --> T --> JOBS
    Q -. "on failure" .-> ALERT
    JOBS -- "fresh, active, de-duplicated" --> API
    USER -- "CV · LinkedIn PDF · GitHub link" --> WEB --> API
    API --> GH
    API -. "rewrite CV text" .-> LLM
    API -- "matches · skill gaps · salaries · CV files" --> WEB --> USER
```

## 2. The daily ETL (Airflow DAG `seekjobs_daily_vacancies`)

```mermaid
flowchart LR
    P["prepare_database<br/>create / upgrade tables"] --> E1["extract_devkz_jobs"] & E2["extract_itvacancykz"] & E3["extract_halyk_jumys"] & E4["extract_… (one per channel)"]
    E1 & E2 & E3 & E4 --> TL["transform_load<br/>(runs even if one channel failed)"]
    TL --> EX["expire_old_jobs<br/>&gt; 45 days → hidden"] --> QC["quality_check<br/>fails loudly if data looks wrong"]
```

- 3 channels are fetched at a time (polite to Telegram); a failed channel is retried twice, 10 minutes apart.
- Each run re-reads the last 7 days of every channel, so **edited** posts are updated and **deleted** posts disappear.
- The same steps run without Airflow: `cd pipeline && python run_daily.py`.

## 3. Life of one vacancy

```mermaid
stateDiagram-v2
    [*] --> Posted: company posts in a channel
    Posted --> Collected: extract (saved to raw_posts)
    Collected --> Skipped: not a vacancy (CV post, ad, event)
    Collected --> Active: vacancy → title, company, city, salary, level, skills
    Active --> Active: post edited → fields updated
    Active --> Closed: post edited to "вакансия закрыта"
    Active --> Deleted: post removed from the channel
    Active --> Expired: older than 45 days
    Closed --> [*]
    Deleted --> [*]
    Expired --> [*]
    Skipped --> [*]
```

Only **Active** jobs are shown on the site; the same job reposted in several channels is shown once.

## 4. What a job seeker does

```mermaid
sequenceDiagram
    actor U as Job seeker
    participant W as Website
    participant A as Backend API
    participant D as Jobs database
    participant L as LLM (optional)

    U->>W: upload CV / LinkedIn PDF, add GitHub link
    W->>A: POST /api/analyze
    A->>A: read files, find skills & level
    A->>D: fresh jobs (last 45 days)
    A-->>W: best matches: score, skill gaps, salary vs market, job link
    U->>W: "Generate CV" for one job
    W->>A: POST /api/cv/generate
    A-->>L: rewrite for this job (only if a key is set)
    A-->>W: tailored CV (only real facts)
    U->>W: download
    W->>A: POST /api/cv/export (PDF / Word)
    A-->>U: file
    U->>U: applies via the job link
```

## 5. Project roadmap

```mermaid
flowchart LR
    P0["Phase 0 ✅<br/>cleanup"] --> P1["Phase 1 ✅<br/>MVP end to end<br/>matching · PDF/Word · tests · CI"]
    P1 --> P2["Phase 2 ✅<br/>data engine<br/>Telegram ETL · Postgres · Airflow"]
    P2 --> P3["Phase 3<br/>product<br/>accounts · application tracker<br/>RU/KZ/EN · Telegram bot"]
    P3 --> P4["Phase 4<br/>validate<br/>pilots with universities<br/>& bootcamps"]
    P4 --> P5["Phase 5<br/>monetize<br/>freemium + B2B licences<br/>salary reports"]
```
