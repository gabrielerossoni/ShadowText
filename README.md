# Shadow Text

Sistema locale per censurare file messi in `Censura`, salvare i dati originali
in `Dati`, e ripristinare i file quando il censurato viene spostato in
`Riunione`.

Usa:

- `openai/privacy-filter` tramite `opf`;
- regex locali per IBAN, email, telefoni, URL e aziende con suffisso legale;
- memoria persistente in `Dati/memoria.json`;
- audit in `Dati/storico.jsonl`.

## Installazione

Dalla cartella principale del progetto:

```powershell
cd ShadowText
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Al primo avvio, `openai/privacy-filter` puo scaricare il modello in:

```text
C:\Users\Gab\.opf\privacy_filter
```

## Avvio watcher

Comando consigliato per uso normale:

```powershell
python -m shadow_text watch --fast-pdf
```

Questo usa OPF su `.txt` e `.md`, ma sui PDF usa regex + memoria. E il miglior
compromesso se i PDF devono essere veloci.

Per default, ogni modalita che usa OPF prova automaticamente CUDA/GPU su tutti i
file. Se CUDA non e disponibile o OPF non riesce a usarla, torna su CPU.

Tutti i modi di avvio:

```powershell
python -m shadow_text watch
```

Modalita completa. Usa OPF su tutti i file supportati. E la piu precisa. Prova
CUDA/GPU; se non riesce torna su CPU.

```powershell
python -m shadow_text watch --fast-pdf
```

Modalita consigliata. PDF veloci con regex + memoria; txt/md con OPF. I txt/md
provano CUDA/GPU. I PDF in questa modalita non usano OPF, quindi non usano GPU.

```powershell
python -m shadow_text watch --regex-only
```

Modalita veloce senza OPF. Usa solo regex + memoria per tutti i file.

```powershell
python -m shadow_text watch --gpu-over-mb 5
```

Limita l'uso automatico della GPU ai file sopra 5 MB:

```powershell
python -m shadow_text watch --gpu-over-mb 0
```

Disattiva la soglia automatica e usa il device normale.

```powershell
python -m shadow_text watch --fast-pdf --gpu-over-mb 5
```

PDF veloci senza OPF; txt/md sopra 5 MB provano GPU.

```powershell
python -m shadow_text watch --all-files
```

Prova a leggere anche estensioni non note come testo UTF-8.

Il vecchio package interno `censura_privacy` resta compatibile, quindi i vecchi
comandi continuano a funzionare. Per il rebranding usa pero i comandi
`shadow_text`.

Se sei per errore dentro `censura_privacy`, funziona ancora anche:

```powershell
python watcher.py watch --fast-pdf
```

## CUDA/GPU

Controllare se il Python usato dal progetto vede CUDA:

```powershell
python -m shadow_text doctor-cuda
```

Se `nvidia-smi` vede la GPU ma `doctor-cuda` mostra `torch.version.cuda = None`
oppure `torch.cuda.is_available() = False`, il problema e PyTorch installato
senza supporto CUDA nel Python che stai usando.

Reinstalla PyTorch con CUDA dopo le dipendenze del progetto:

```powershell
python -m pip install -r requirements.txt
python -m pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
python -m shadow_text doctor-cuda
```

Quando `doctor-cuda` mostra `torch.cuda.is_available(): True`, OPF puo usare la
GPU. Se CUDA fallisce durante la censura, il watcher stampa il motivo reale e fa
fallback su CPU.

Se compare un errore del tipo:

```text
Triton-backed MoE kernels require the optional `triton` dependency.
Install `triton` or unset OPF_MOE_TRITON.
```

Shadow Text forza automaticamente `OPF_MOE_TRITON=0` se `triton` non e
installato, poi riprova OPF su CUDA. Questo serve perche OPF abilita i kernel
Triton di default sui device non CPU: lasciare la variabile non impostata non
basta. In pratica non devi installare `triton` per questo caso su Windows:
riavvia il watcher dopo aver aggiornato il codice.

## Cosa succede

1. Metti un file in `Censura`.
2. Il watcher crea `nome.censurato.ext`.
3. L'originale viene spostato in `Dati/Originali`.
4. Il mapping tag -> valore originale viene scritto in `Dati/*.json`.
5. Sposti `nome.censurato.ext` in `Riunione`.
6. Il watcher crea `nome.ripristinato.ext`.
7. Il file censurato viene rimosso da `Riunione`.

Importante: `Riunione` non censura file normali. Se metti `documento.pdf` in
`Riunione`, viene ignorato. In `Riunione` vanno solo file con `.censurato` nel
nome, ad esempio `documento.censurato.pdf`.

Esempio:

```text
Censura/nota.pdf
-> Censura/nota.censurato.pdf
-> Dati/nota.censurato.pdf.json
-> Dati/Originali/nota.pdf

Riunione/nota.censurato.pdf
-> Riunione/nota.ripristinato.pdf
```

## Log

Il watcher mostra cosa sta facendo:

```text
[23:14:02] Watcher attivo
[23:14:02] Censura: nota.pdf (329104 byte)
[23:14:07] Dati sensibili trovati: 4
[23:14:08] File censurato pronto: nota.censurato.pdf
[23:14:08] OK censura: nota.censurato.pdf (6.1s)
```

## Formati supportati

- `.txt`
- `.md`
- `.markdown`
- `.pdf`

I PDF restano PDF. Il sistema usa `PyMuPDF` per applicare redazioni sulle pagine
originali: mantiene numero di pagine e dimensioni pagina.

## Come gestire i PDF

Per censurare un PDF:

```text
Censura/documento.pdf
-> Censura/documento.censurato.pdf
```

Poi sposta il PDF censurato in `Riunione` solo quando vuoi ripristinarlo:

```text
Riunione/documento.censurato.pdf
-> Riunione/documento.ripristinato.pdf
```

Non rimettere `documento.censurato.pdf` in `Censura`: il watcher lo ignora e ti
dice di spostarlo in `Riunione`.

## Comandi singolo file

Censurare un file specifico:

```powershell
python -m shadow_text censor --file .\Censura\nota.pdf --fast-pdf
```

Ripristinare un file specifico:

```powershell
python -m shadow_text restore --file .\Riunione\nota.censurato.pdf
```

## Aumentare la memoria

La memoria serve a correggere gli errori e rendere stabile il comportamento nei
file successivi.

Vedere la memoria:

```powershell
python -m shadow_text show-memory
```

Se manca una censura, aggiungi una regola:

```powershell
python -m shadow_text remember-redact --text "Mario Rossi" --label private_person
```

Esempi utili:

```powershell
python -m shadow_text remember-redact --text "IT60X0542811101000000123456" --label iban
python -m shadow_text remember-redact --text "mario.rossi@example.com" --label private_email
python -m shadow_text remember-redact --text "+39 333 1234567" --label private_phone
python -m shadow_text remember-redact --text "Via Roma 10, Milano" --label private_address
python -m shadow_text remember-redact --text "API_KEY_123456789" --label secret
```

Per aziende:

```powershell
python -m shadow_text remember-company --text "OpenAI"
python -m shadow_text remember-company --text "Rossi Consulting"
```

Se censura qualcosa che deve restare visibile:

```powershell
python -m shadow_text remember-keep --text "OpenAI"
```

Le regole vengono salvate in:

```text
Dati/memoria.json
```

## Label utili

```text
private_person
private_email
private_phone
private_address
private_date
private_url
account_number
secret
iban
company
organization
tax_code
vat_number
```

Tag generati:

```text
PERSONA_00001
EMAIL_00001
TELEFONO_00001
INDIRIZZO_00001
DATA_00001
URL_00001
CONTO_00001
SEGRETO_00001
IBAN_00001
AZIENDA_00001
```

## File creati

```text
Dati/memoria.json              memoria delle correzioni
Dati/storico.jsonl             audit
Dati/Originali/*               originali archiviati
Dati/*.censurato.*.json        mapping tag -> valore originale
Censura/*.censurato.*          file censurati
Riunione/*.ripristinato.*      file ripristinati
```

`Dati` contiene materiale sensibile. Non condividerla e non committarla.

## Note

`openai/privacy-filter` aiuta a minimizzare dati sensibili, ma non garantisce
anonimizzazione perfetta. Per documenti importanti: censura, controlla il file,
aggiungi regole in memoria, poi ricensura dagli originali in `Dati/Originali`.


