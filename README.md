# portfolio-performance-broker-taxonomy


#### English [Česká verze](#Česká-verze-english)
## Automatically Recalculate Security Weights in a Portfolio Performance Taxonomy

A Python script for automatically recalculating security weights in a [Portfolio Performance](https://www.portfolio-performance.info/) taxonomy based on the number of units held with each broker.

### What is this script for?

Portfolio Performance does not automatically recalculate security weights in a taxonomy based on how a security is distributed across different brokers.

This Python script automatically recalculates the security weights in a Portfolio Performance taxonomy named `Podle brokera` (By Broker).

It is intended for portfolios where the same security is held at multiple brokers. Instead of manually adjusting the weights in the taxonomy, the script calculates them from the actual quantities held at each broker.

**Important:** The weights are calculated from the number of shares held, not from their market value or price.

For example, if you hold 6 shares at Degiro and 4 shares at XTB, the resulting weights will be 60% and 40%.

### What does the script do?

- Reads portfolio transaction history and calculates current security holdings for each broker.
- Processes purchases, sales and supported security transfers.
- Handles both sides of transfers between securities accounts, so that a transfer between brokers does not change the total number of shares held.
- Recalculates the weights of existing security assignments.
- Creates missing security assignments when a security is held at a broker but has not yet been assigned to that broker's taxonomy class.
- Removes obsolete security assignments when transaction history confirms that the position at that broker has fallen to zero.
- Preserves existing assignments if there is no transaction history to confirm a zero balance. The script does not assume that missing history means zero holdings.
- Ensures that the weights of each held security add up to exactly 100%.
- Checks that no changes have been made outside the target taxonomy.

The script displays a summary of the detected transactions and proposed changes before asking for confirmation.

### Requirements

- Python 3
- No third-party Python packages are required; the script uses only the Python standard library.
- Portfolio Performance must be closed before running the script.

The script has been tested with Portfolio Performance 0.89.0. Compatibility with other versions and portfolio configurations is not guaranteed.

### Configuration

Before running the script, open it in a text editor and adjust the settings near the beginning of the file.

**`PORTFOLIO_FILE`**

Path to your Portfolio Performance file.

Example:

```python
PORTFOLIO_FILE = r"C:\Users\Jane\Investments.portfolio"
```

The script supports both the standard `.zip` archive and a standalone XML file.

**`TAXONOMY_NAME`**

Name of the taxonomy to be updated. The default is:

```python
TAXONOMY_NAME = "Podle brokera"
```

The taxonomy must already exist in Portfolio Performance, and its broker classifications must already be created.

**`PORTFOLIO_SUFFIX`**

Suffix automatically removed from securities account names when determining the corresponding broker name.

The default is:

```python
PORTFOLIO_SUFFIX = " Portfolio"
```

For example, `Degiro Portfolio` is mapped to the taxonomy classification `Degiro`.

Account names without this suffix are used as they are.

**`PORTFOLIO_TO_BROKER`**

Optional manual mapping of securities account names to taxonomy classification names.

Use this setting if an account name does not match the corresponding broker classification after removing the configured suffix.

Example:

```python
PORTFOLIO_TO_BROKER = {
    "My crypto wallet": "Coinbase",
    "Special account": "My broker"
}
```

The account name must match exactly. Manual mappings take precedence over automatic name processing.

**Backup and log settings**

- `BACKUPS_TO_KEEP` determines how many backups are retained (default: 10).
- `BACKUP_MARKER` defines the text used in backup filenames.
- `LOG_SUFFIX` defines the text included in log filenames.

These settings can normally be left unchanged.

### Running the script

1. Close Portfolio Performance.
2. Set the correct path to your portfolio file and check the account mappings.
3. Run the script using Python 3.
4. Review the transaction summary and proposed taxonomy changes.
5. To save the changes, type `YES` exactly when prompted. Any other response cancels the operation.

### Safety and limitations

The script is designed to avoid modifying portfolio data outside the target taxonomy.

Before replacing the original file, it:

- Constructs the modified file in a temporary location.
- Validates the resulting XML or ZIP archive.
- Checks that no data outside the target taxonomy has changed.
- Creates a backup of the original file.
- Replaces the original file using an atomic operation.

Older backups are automatically removed when the configured retention limit is exceeded.

A text log is also created alongside the portfolio file. It contains the script's output, including the transaction summary and any detected errors.

The script stops without replacing the original file if it encounters unsupported transaction types, missing broker classifications, inconsistent holdings or failed validation.

**Important limitations:**

- The script relies on the transaction history stored in the portfolio file. Its results therefore depend on the completeness and correctness of that history.
- If securities were transferred between brokers, check that Portfolio Performance records the transfers using transaction types supported by the script.
- The script does not create missing broker classifications. They must already exist in the target taxonomy.
- Always keep your own backup of the portfolio file before using the script, especially when trying it for the first time.

### Why was this script created?

I wanted to maintain a `Podle brokera` (By Broker) taxonomy in Portfolio Performance without having to manually recalculate security weights whenever I bought, sold or transferred securities between brokers.

The script automates this process using the transaction history and the actual number of shares held at each broker.

### Disclaimer

This script is provided "as is", without any warranty. Use it at your own risk. Always keep a separate backup of your portfolio data.

The script is a community contribution and is not an official part of Portfolio Performance. No ongoing support or compatibility with future Portfolio Performance versions is guaranteed.

-------------
#### Česká verze [English](#english-česká-verze)
## Automatický přepočet vah cenných papírů v taxonomii Portfolio Performance

Python skript pro automatický přepočet vah cenných papírů v taxonomii podle počtu kusů u jednotlivých brokerů v programu [Portfolio Performance](https://www.portfolio-performance.info/).

### K čemu skript slouží?

Portfolio Performance samo automaticky nepřepočítává váhy v taxonomii podle aktuální hodnoty pozic. Při změně portfolia je proto nutné váhy ručně upravovat.

Tento Python skript automaticky přepočítává váhy cenných papírů v taxonomii Portfolio Performance s názvem `Podle brokera`.

Je určen pro portfolia, ve kterých je stejný cenný papír držen u více brokerů. Namísto ručního upravování vah v taxonomii skript vypočítá jejich rozdělení podle skutečného množství držených kusů u jednotlivých brokerů.

**Důležité:** Váhy se počítají podle počtu držených kusů, nikoli podle jejich tržní hodnoty nebo ceny.

Například pokud držíš 6 kusů u Degiro a 4 kusy u XTB, výsledné váhy budou 60 % a 40 %.

### Co skript dělá?

- Načítá historii transakcí portfolií a vypočítává aktuální množství držených cenných papírů u jednotlivých brokerů.
- Zpracovává nákupy, prodeje a podporované převody cenných papírů.
- Zohledňuje obě strany převodů mezi účty cenných papírů, takže převod mezi brokery nemění celkové množství držených kusů.
- Přepočítává váhy stávajících přiřazení cenných papírů.
- Vytváří chybějící přiřazení cenných papírů, pokud je daný cenný papír u brokera držen, ale dosud není přiřazen k jeho klasifikaci v taxonomii.
- Odstraňuje zastaralá přiřazení, pokud historie transakcí potvrzuje, že množství držené u daného brokera kleslo na nulu.
- Zachovává stávající přiřazení, pokud není k dispozici historie transakcí potvrzující nulový zůstatek. Nepředpokládá tedy automaticky, že chybějící historie znamená nulové držení.
- Zajišťuje, aby součet vah každého drženého cenného papíru činil přesně 100 %.
- Kontroluje, zda nedošlo ke změnám mimo cílovou taxonomii.

Před potvrzením uložení skript zobrazí souhrn zjištěných transakcí a navrhovaných změn.

### Požadavky

- Python 3
- Nejsou potřeba žádné další Python balíčky; skript využívá pouze standardní knihovnu Pythonu.
- Před spuštěním skriptu musí být Portfolio Performance zavřené.

Skript byl testován s Portfolio Performance 0.89.0. Kompatibilita s jinými verzemi a konfiguracemi portfolia není zaručena.

### Nastavení

Před spuštěním otevři skript v textovém editoru a uprav nastavení na začátku souboru.

**`PORTFOLIO_FILE`**

Cesta k souboru Portfolio Performance.

Příklad:

```python
PORTFOLIO_FILE = r"C:\Users\Jane\Investments.portfolio"
```

Skript podporuje standardní archiv `.zip` i samostatný XML soubor.

**`TAXONOMY_NAME`**

Název taxonomie, která se má aktualizovat. Výchozí nastavení je:

```python
TAXONOMY_NAME = "Podle brokera"
```

Taxonomie musí v Portfolio Performance již existovat a musí v ní být vytvořené klasifikace jednotlivých brokerů.

**`PORTFOLIO_SUFFIX`**

Přípona, která se automaticky odstraní z názvů účtů cenných papírů při určování odpovídajícího názvu brokera.

Výchozí nastavení je:

```python
PORTFOLIO_SUFFIX = " Portfolio"
```

Například účet `Degiro Portfolio` se převede na klasifikaci `Degiro`.

Názvy účtů bez této přípony se použijí beze změny.

**`PORTFOLIO_TO_BROKER`**

Volitelné ruční mapování názvů účtů cenných papírů na názvy klasifikací v taxonomii.

Použij toto nastavení, pokud název účtu neodpovídá názvu klasifikace brokera ani po odstranění nastavené přípony.

Příklad:

```python
PORTFOLIO_TO_BROKER = {
    "Moje krypto peněženka": "Coinbase",
    "Speciální účet": "Můj broker"
}
```

Název účtu musí přesně odpovídat. Ruční mapování má přednost před automatickým zpracováním názvu.

**Nastavení záloh a protokolu**

- `BACKUPS_TO_KEEP` určuje počet uchovávaných záloh (výchozí hodnota: 10).
- `BACKUP_MARKER` určuje text použitý v názvech záložních souborů.
- `LOG_SUFFIX` určuje text obsažený v názvech protokolů.

Tato nastavení obvykle není nutné měnit.

### Spuštění skriptu

1. Zavři Portfolio Performance.
2. Nastav správnou cestu k souboru portfolia a zkontroluj mapování účtů.
3. Spusť skript pomocí Pythonu 3.
4. Prohlédni si souhrn transakcí a navrhované změny taxonomie.
5. Pokud chceš změny uložit, zadej po výzvě přesně `ANO`. Jakákoli jiná odpověď operaci zruší.

### Bezpečnost a omezení

Skript je navržen tak, aby neměnil data portfolia mimo cílovou taxonomii.

Před nahrazením původního souboru:

- Vytvoří upravený soubor v dočasném umístění.
- Ověří výsledné XML nebo ZIP archiv.
- Zkontroluje, zda se nezměnila žádná data mimo cílovou taxonomii.
- Vytvoří zálohu původního souboru.
- Nahradí původní soubor pomocí atomické operace.

Starší zálohy se automaticky odstraňují, pokud je překročen nastavený limit jejich uchovávání.

Ve stejné složce jako soubor portfolia se také vytváří textový protokol. Obsahuje výstup skriptu, včetně souhrnu transakcí a případných zjištěných chyb.

Pokud skript narazí na nepodporovaný typ transakce, chybějící klasifikaci brokera, nesrovnalosti v drženém množství nebo neúspěšnou kontrolu, ukončí se bez nahrazení původního souboru.

**Důležitá omezení:**

- Skript vychází z historie transakcí uložené v souboru portfolia. Výsledek proto závisí na úplnosti a správnosti této historie.
- Pokud byly cenné papíry převáděny mezi brokery, zkontroluj, zda Portfolio Performance tyto převody zaznamenává pomocí typů transakcí, které skript podporuje.
- Skript nevytváří chybějící klasifikace brokerů. Ty musí být v cílové taxonomii vytvořené předem.
- Před použitím skriptu si vždy ponech vlastní zálohu souboru portfolia, zejména při prvním vyzkoušení.

### Proč skript vznikl?

Chtěl jsem v Portfolio Performance používat taxonomii `Podle brokera`, aniž bych musel ručně přepočítávat váhy cenných papírů pokaždé, když nějaké nakoupím, prodám nebo převedu mezi brokery.

Skript tento proces automatizuje na základě historie transakcí a skutečného počtu držených kusů u jednotlivých brokerů.

### Upozornění

Tento skript je poskytován tak, jak je, bez jakékoli záruky. Používáš ho na vlastní riziko. Vždy si ponech samostatnou zálohu dat svého portfolia.

Skript je komunitním příspěvkem a není oficiální součástí Portfolio Performance. Není zaručena průběžná podpora ani kompatibilita s budoucími verzemi Portfolio Performance.
