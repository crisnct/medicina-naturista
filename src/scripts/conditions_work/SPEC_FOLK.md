# Sarcina FOLK — denumiri populare si argou pentru fiecare boala

Primesti o lista de boli (cate una pe linie). Pentru fiecare boala cauti **cum ii spune
lumea in romana vorbita**: denumire populara, regionalism, argou medical, termen vechi
folosit de batrani, uneori chiar o injuratura sau un termen vulgar.

## Ce scrii

Un fisier cu linii de forma:

```
NumeCanonic|denumire populara
```

- `NumeCanonic` = exact numele din lista primita, scris **identic** (primul camp).
- `denumire populara` = termenul popular/argotic, **fara diacritice** (`galbeaza`, nu `gălbează`).
- **Fara virgula** in denumirea populara. Maxim ~40 de caractere.
- Daca o boala are **mai multe** denumiri populare cunoscute, scrie **mai multe linii** cu acelasi
  nume canonic (ex. `Tuberculoza|oftica` si `Tuberculoza|ftizie`).
- Daca boala **nu are** denumire populara, **nu scrie nimic** pentru ea. Mai bine 100 de linii
  reale decat 400 inventate.

## Reguli de substanta

1. **Numai termeni reali, atestati.** Nu inventa si nu compune termeni de tipul
   `boala care iti ia somnul`. Daca nu esti sigur ca termenul exista in vorbirea romaneasca,
   nu il scrie.
2. Sunt acceptate: denumiri traditionale (`jinduitul`, `galbeaza`, `oftica`, `lingoare`, `raie`),
   termeni vechi/rareori scrise (`buba coapta`, `naduful`, `pirostrii`), argou medical
   (`piatra la fiere`, `cheag la picior`, `zahar`), argou de spital, si termeni vulgari
   pentru boli jenante (`boala rusinoasa` = BTS, `buba` = sifilis/gonoree dupa caz).
3. Termenii vulgari sau jignitori sunt **acceptati** daca sunt real folositi de oameni pentru
   boala respectiva. Scrie-i exact asa cum se spun.
4. Nu pune termen medical ca „popular" (`miocardita` nu e popular pentru infarct).
5. **Un termen popular apartine unei singure boli.** Daca acelasi termen s-ar potrivi la doua
   boli din lista ta (ex. `buba` la abces si la sifilis, `chelia` la alopecie si la pelada),
   da-l bolii celei mai reprezentative si sari peste la cealalta. Nu repeta termenul.
6. Nu repeta numele canonic ca denumire populara.

## Unde scrii

In fisierul indicat in sarcina ta. Doar liniile de date, fara titluri, fara linii goale, fara ``` .
