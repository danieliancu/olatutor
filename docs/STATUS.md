# Starea proiectului

**Ultima actualizare:** 2026-11-03, după adăugarea site-ului de prezentare.

Acesta e fișierul de urmărit. Se actualizează la finalul fiecărui milestone și ori de câte ori se schimbă o decizie sau un blocaj. Dovezile detaliate sunt în [PROGRESS.md](PROGRESS.md).

**Pe scurt:** caietul digital funcționează în browser, cu mai multe pagini, dar a fost testat doar cu input simulat. Nu există încă recunoaștere de scris, notare, conturi sau firmware. Prototipul nu are autentificare și trebuie să rămână local.

Stări folosite: **PASS**, **PARTIAL**, **BLOCKED**, **FAIL**, plus **Neînceput**.

## Milestone-uri

| # | Milestone | Stare | Ce îl blochează |
|---|---|---|---|
| 0 | Contracte tehnice și prototip de cerneală | **PASS** | – |
| 1 | Caiet funcțional | **PASS** (input simulat) | – |
| 2 | Fezabilitate hardware (placa ELECROW) | **BLOCKED** | Placa nu e disponibilă |
| 3 | Recunoaștere și semantica paginii | Neînceput | Pentru rezultate oneste: scriitori adulți care consimt |
| 4 | Matematică și feedback pe pagină | Neînceput, **recomandat următorul** | – |
| 5 | Familii și pilot | Neînceput | Pentru date reale despre copii: DPIA și revizie juridică |
| 6 | Materiale de la părinți și voce | Neînceput | – |
| 7 | AI controlat și comercializare | Neînceput | – |

## Ce ai de făcut sau de decis

- [ ] **Alegi următorul milestone.** Recomandarea mea e Milestone 4.
- [x] **Numele „olátutor”** e confirmat. Footerul folosește firma și adresa de contact de la olacompanion.
- [ ] **Pagini legale pentru site** (confidențialitate, termeni): nu există încă. Cele de la olacompanion sunt scrise pentru ceas, așa că nu le-am legat.
- [ ] **Testezi cu un stilou real pe o tabletă,** după pașii din [README](../README.md). Durează puțin și poate schimba designul.
- [ ] **Când ajunge placa:** îmi spui revizia scrisă pe ea (V1.0, V1.1 sau V1.2) și ce stilou ai.
- [x] **Commit și remote:** codul e pe <https://github.com/danieliancu/olatutor> (repo public).
- [ ] **Confirmi pragurile propuse pentru recunoaștere** (vezi [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)). Trebuie fixate înainte de colectarea datelor: acuratețe brută ≥85%, corecturi la ≤15% din răspunsuri, ≥95% din erorile introduse intenționat sunt prinse.
- [ ] **Găsești scriitori adulți pentru Milestone 3.** Sunt necesari cam 30 ca să demonstrăm ținta de 95% acuratețe. Scrisul tău poate fi folosit la dezvoltare, nu la testul final.
- [ ] **Înainte de pilot: revizie juridică și DPIA.** Întrebările deschise sunt în [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md).

## Ce funcționează acum

- [x] Scris liber pe pagină, cu mouse sau stilou
- [x] Radieră care taie stroke-urile, undo și redo
- [x] Mai multe pagini, portret sau landscape, și ștergere cu confirmare
- [x] Zoom până la 200% și unealta „Move page”
- [x] Salvare locală în IndexedDB și sincronizare fără duplicate
- [x] Scris offline, cu trimitere la reconectare
- [x] Redeschidere offline a unui caiet deja vizitat, pe `localhost`
- [x] Conflicte între două dispozitive, rezolvate de utilizator, fără pierderi
- [x] Revizii imutabile, verificate cu hash-uri
- [x] Reconstrucția paginii în Python, identică cu cea din browser
- [x] Site de prezentare la `/`, în stilul olacompanion, cu funcțiile marcate clar ca existente sau planificate

## Ce nu există încă

- [ ] Recunoașterea scrisului și înțelegerea paginii
- [ ] Notarea matematică și feedbackul pe pagină
- [ ] Conturi, login, familii, profiluri de copii
- [ ] Dashboard pentru părinți și teme atribuite
- [ ] Curriculum și generarea de exerciții
- [ ] Încărcarea de materiale, vocea, AI, abonamente
- [ ] Firmware pentru placă

Pentru recunoaștere, notare și dispozitiv există doar contractele sau metodologia, nu și implementarea.

## Ultimele rezultate ale testelor

| Suită | Rezultat |
|---|---|
| Python (`pytest`) | 176 trecute, 2 sărite intenționat |
| Conformitate JS (`node --test`) | 110 trecute, 0 eșuate |
| Browser: Chromium, Firefox, WebKit | 81 trecute, 0 eșuate, în două rulări complete la rând |
| Validare contracte | 76 verificări, 0 eșecuri |
| `ruff` și `mypy` | fără erori |

Testele din browser folosesc input simulat. Ele verifică datele și logica, nu confortul scrisului.

## Neverificat sau blocat

| Ce | Stare | Ce ar debloca |
|---|---|---|
| Scrisul cu stilou real, confortul, latența | **BLOCKED** | Test pe o tabletă reală, apoi cu oameni |
| Tablete reale și Safari pe iPad | **BLOCKED** | Acces la dispozitive |
| Redeschidere offline pe tabletă, în rețeaua locală | **BLOCKED** | Configurare cu HTTPS |
| Respingerea palmei | **BLOCKED** | Placa fizică |
| Toate datele despre placă, citite doar din documentație | **BLOCKED** | Placa fizică |
| Acuratețea pe scrisul copiilor | **BLOCKED** | Pilot aprobat, după DPIA |
| CI | **FAIL** la prima rulare, la pasul Lint. Cauza probabilă, reprodusă local: containerul nu poate scrie cache în checkout. Remedierea e în `ci.yml`, neverificată pe GitHub | Push și o rulare nouă |

## Riscuri principale

Lista completă, cu 22 de riscuri, e în [RISK_REGISTER.md](RISK_REGISTER.md).

1. **Stiloul pe ecran capacitiv.** Panoul s-ar putea să nu deosebească stiloul pasiv de palmă. Poate impune altă placă, dar serverul și contractul nu depind de ea.
2. **Scrisul copiilor.** Nu știm dacă un model local îl poate citi suficient de bine.
3. **Înțelegerea paginii întregi.** E mult mai grea decât recunoașterea simbolurilor și s-ar putea să nu atingă o acuratețe utilă.
4. **Date pentru antrenare.** Nu am găsit date de stroke cu licență clară pentru `+ × ÷ = /`.
5. **Alimentarea plăcii.** Documentația indică 8–10 W, iar pe USB ecranul se poate stinge.
6. **Obligațiile legale pentru datele copiilor.** Sunt nerezolvate și cer revizie independentă.

## Limite cunoscute

- Copierea unei versiuni într-o pagină nouă, la conflict, păstrează ce se vede, nu și istoricul.
- Modificările de pe alt dispozitiv apar doar după reîncărcare.
- Pe puncte rare, radiera poate părea mai lată decât este.
- Reconstrucția unei pagini foarte lungi durează câteva secunde (aproape 3 s la 2.000 de operații).
- Jurnalul local și carantina de pe server cresc fără limită.

## Cum pornești proiectul

```powershell
docker compose up -d --build --wait web
```

Apoi deschizi <http://localhost:8000/notebook/>. Pașii compleți și comenzile de test sunt în [README](../README.md).

## Istoric

| Data | Ce s-a întâmplat |
|---|---|
| 2026-11-02 | Milestone 0 încheiat: contracte și prototip |
| 2026-11-02 | Milestone 2 blocat: placa nu e disponibilă. Am continuat cu ce nu depinde de hardware |
| 2026-11-02 | Milestone 1 încheiat: caiet cu mai multe pagini, pe trei motoare de browser |
| 2026-11-03 | Primul commit și legarea la GitHub |
| 2026-11-03 | Site de prezentare adăugat, fără conturi și fără dashboard |
