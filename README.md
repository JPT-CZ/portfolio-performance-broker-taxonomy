# portfolio-performance-broker-taxonomy

[Česká verze](#Česká-verze)
# Automatically Recalculate Security Weights in a Portfolio Performance Taxonomy

## What is this script for?

Portfolio Performance does not automatically recalculate security weights in a taxonomy based on how a security is distributed across different brokers.

This Python script automates this process for a taxonomy named **"Podle brokera"** (By Broker). It calculates the current holdings of each security at individual brokers and adjusts the corresponding taxonomy weights accordingly.

## What does the script do?

- Calculates current security holdings at individual brokers based on transaction history.
- Takes purchases, sales and supported types of transfers into account.
- Recalculates the weights of securities in the target taxonomy according to the number of shares held at each broker.
- Creates missing security assignments in the taxonomy when necessary.
- Removes outdated assignments only when the transaction history confirms that the holding has been reduced to zero.
- Checks balances and verifies expected changes.
- Checks that changes correspond to the expected modifications of the target taxonomy.
- Creates a backup of the original portfolio file before making any changes.
- Saves a log file containing a summary of the changes.

## Requirements and setup

- Python 3 is required.
- No additional Python packages need to be installed. The script uses only the Python standard library.
- **Portfolio Performance must be closed before running the script.**

The script has been tested with a Portfolio Performance file created using version **0.89.0**.

It supports both the standard Portfolio Performance archive (`.portfolio`) and a standalone XML file.

Compatibility with all Portfolio Performance versions and configurations is not guaranteed.

## Account names and taxonomy classifications

The script identifies brokers based on the names of securities accounts.

For example:

- An account named `Degiro Portfolio` is assigned to the `Degiro` classification.
- An account named `Degiro` is also assigned to the `Degiro` classification.

By default, the script removes the suffix ` Portfolio` from the account name to obtain the broker name.

If an account name does not correspond to the desired taxonomy classification, you can define a manual mapping in the script configuration.

## Configuration

The script contains several configurable settings near the beginning of the file.

For example, you can specify:

- The path to your Portfolio Performance file.
- The name of the target taxonomy.
- The number of backups to keep.
- The suffix used in log filenames.
- Manual mappings between securities account names and taxonomy classifications.

The configuration options are explained by comments directly in the script.

## Input file

Set the `PORTFOLIO_FILE` variable to the path of your Portfolio Performance file.

Make sure that the file is not open in Portfolio Performance when you run the script.

## Safety and limitations

The script is designed to avoid unintended changes to your portfolio file.

Before making any changes, it displays a summary and requires you to enter the exact confirmation `YES`.

It creates a backup of the original file and validates the modified file before replacing the original.

The script also checks that no unintended changes have been made outside the target taxonomy. If an unexpected change is detected, the process is stopped.

The results depend on the accuracy and completeness of the transaction data in your Portfolio Performance file.

## Why was this script created?

I created this script because I wanted Portfolio Performance to automatically adjust security weights in a taxonomy according to how the securities are distributed across different brokers.

Since this functionality is not available directly in Portfolio Performance, I decided to create a solution using Python with the assistance of ChatGPT.

I am sharing the script with the Portfolio Performance community in case it may be useful to others.

## Disclaimer

The script is provided **"as is"**, without any warranty.

I cannot guarantee that it will work in every environment or with every Portfolio Performance file. I also cannot provide ongoing support or guarantee compatibility with future versions of Portfolio Performance.

Always keep a backup of your portfolio file before using the script.

-------------
#### Česká verze
# Automatický přepočet vah cenných papírů v taxonomii Portfolio Performance

Python skript pro automatický přepočet vah cenných papírů v taxonomii podle jejich aktuální hodnoty u jednotlivých brokerů v programu [Portfolio Performance](https://www.portfolio-performance.info/).

## K čemu skript slouží

Pokud držíš stejné ETF nebo jiné cenné papíry u více brokerů, můžeš v Portfolio Performance vytvořit taxonomii, která ukazuje, jakou část portfolia máš u každého brokera.

Portfolio Performance ale samo automaticky nepřepočítává váhy v taxonomii podle aktuální hodnoty pozic. Při změně portfolia je proto nutné váhy ručně upravovat.

Tento skript tento proces automatizuje. Zpracuje údaje o držených cenných papírech a přepočítá jejich váhy v určené taxonomii podle jednotlivých brokerů.

## Co skript dělá

- Zjišťuje množství držených cenných papírů v jednotlivých investičních účtech.
- Přepočítává váhy cenných papírů v cílové taxonomii podle jejich rozdělení mezi brokery.
- Zohledňuje nákupy, prodeje a podporované typy převodů cenných papírů.
- Při převodu cenných papírů mezi investičními účty zohledňuje přesun pozice mezi brokery.
- Kontroluje zůstatky a ověřuje očekávané změny.
- Umožňuje aktualizovat váhy bez nutnosti ručně počítat hodnoty a upravovat jednotlivá procenta v taxonomii.
- Kontroluje, zda změny odpovídají očekávaným úpravám cílové taxonomie.
- Vytváří zálohu původního souboru před jeho úpravou.
- Ukládá výpis provedených změn také do textového souboru protokolu.

Skript je určen pro aktualizaci konkrétní taxonomie, nikoli pro změnu ostatních částí portfolia.

## Požadavky a nastavení

- Python.
- Datový soubor Portfolio Performance.
- Taxonomie určená k automatickému přepočtu vah.
- Správně přiřazené investiční účty a odpovídající klasifikace v taxonomii.

**Před spuštěním skriptu musí být Portfolio Performance vypnuté.** Skript přímo upravuje datový soubor programu, takže při současném otevření programu by mohlo dojít ke konfliktu změn.

### Názvy účtů a klasifikací

Skript přiřazuje investiční účty ke klasifikacím v cílové taxonomii podle jejich názvů.

Například účet `Degiro Portfolio` může odpovídat klasifikaci `Degiro`. Účet se ale může jmenovat také přímo `Degiro`, tedy stejně jako příslušná klasifikace.

Před použitím je důležité zkontrolovat názvy účtů a klasifikací a ujistit se, že odpovídají očekávanému formátu skriptu.

### Konfigurace

Skript obsahuje několik nastavení, která lze upravit přímo v jeho zdrojovém kódu. Patří mezi ně například přípona názvu souboru s protokolem změn.

Důležité části kódu jsou opatřeny komentáři, které usnadňují orientaci a případné úpravy nastavení.

### Vstupní soubor

Skript byl vyvinut a testován se souborem Portfolio Performance ve formátu komprimovaného XML (`.zip`) z verze 0.89.0. Podporováno je také zpracování samostatného XML souboru.

Funkčnost v jiných verzích Portfolio Performance nebo ve všech možných konfiguracích není zaručena.

## Bezpečnost a omezení

Skript upravuje pouze určenou taxonomii a kontroluje, zda nedošlo k neočekávaným změnám mimo ni. Před zápisem vytváří zálohu původního souboru.

Přesto doporučuji nejprve vyzkoušet skript na kopii souboru a zkontrolovat výsledky.

Výsledky závisejí na správnosti údajů uložených v souboru Portfolio Performance.

## Proč skript vznikl

Chtěl jsem zobrazit rozdělení svých investic mezi jednotlivé brokery pomocí taxonomie v Portfolio Performance, aniž bych musel při každé změně portfolia ručně přepočítávat váhy.

Protože program tuto funkci automaticky nenabízí, vytvořil jsem tento skript pomocí Pythonu s pomocí ChatGPT. Rozhodl jsem se jej sdílet s komunitou v naději, že by mohl být užitečný i dalším uživatelům.

Skript je poskytován tak, jak je (*as-is*). Nemohu zaručit jeho funkčnost ve všech prostředích ani poskytovat průběžnou podporu.
