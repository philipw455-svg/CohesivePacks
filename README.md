# CohesivePacks Card Lister

This program turns iPhone photos of football cards into eBay auctions.

1. You photograph each card: front first, then back.
2. Photoroom's AI turns each photo into a clean studio shot.
3. Claude's AI reads each card's player, year, set, number, and condition.
4. The program looks up current eBay prices for each card.
5. The program estimates a quick-sale value and a store cash value.
6. You check every card in a spreadsheet.
7. The program posts each approved card as a 3-day eBay auction.

## What you need

| Item | Where you get it | Cost |
|---|---|---|
| eBay developer account | developer.ebay.com | Free |
| Anthropic API key (Claude reads cards) | console.anthropic.com | A few cents per card |
| Photoroom API key (studio photos) | photoroom.com/api | Paid per photo; check their price page |
| Python 3.10 or newer | python.org | Free |

Photoroom is optional. Without it, a free editor only fixes brightness and sharpness.

## One-time setup

### 1. Install the program

Open Terminal (Mac) or PowerShell (Windows) in this folder. Type:

```
python -m venv .venv
source .venv/bin/activate        (Mac)
.venv\Scripts\activate           (Windows)
pip install -r requirements.txt
```

### 2. Fill in your settings

1. Copy `.env.example` to a new file named `.env`.
2. Open `.env` in a text editor.
3. Paste in your keys.

The `.env` file stays on your computer. Git never uploads it.

### 3. Get your eBay keys

1. Sign in at developer.ebay.com.
2. Open **Application Keys**.
3. Create a **Sandbox** key set first. The sandbox is eBay's practice site.
4. Copy the App ID, Dev ID, and Cert ID into `.env`.
5. Open **User Tokens** and create a **RuName**. Copy it into `EBAY_RUNAME`.
6. Create a **Production** key set too. Put its App ID and Cert ID in `PRICING_APP_ID` and `PRICING_CERT_ID`.

The sandbox has no real cards for sale. So price lookups always use the production keys.

### 4. Connect your eBay seller account

```
python -m cardlister login
```

The program shows a web address. You open it, sign in, and click Agree. Then you paste the next page's address back into the program.

### 5. Set up seller policies

1. Create payment, return, and shipping policies in eBay Seller Hub.
2. Run `python -m cardlister policies`.
3. Copy one ID of each kind into `.env`.

### 6. Save your ship-from address

```
python -m cardlister location
```

## Taking photos on your iPhone

- Shoot each card **front first, then back**. The program pairs photos in that order.
- Claude also checks which side is the front, so one mix-up is fine.
- Fill most of the frame with the card.
- Use even light and avoid glare on shiny cards.
- Your dark wood background works well with Photoroom.
- Copy all photos into the `inbox` folder.

The iPhone saves HEIC photos. The program reads them through `pillow-heif`. You can also pick **Settings > Camera > Formats > Most Compatible** for JPEG photos.

## Everyday use

### Step 1: Process the photos

```
python -m cardlister process
```

Try `--limit 3` first to test three cards.

The program saves each card's photos in `output/cards/`. It moves finished photos into `inbox/done/`. It moves failed photos into `inbox/failed/`.

### Step 2: Check the review sheet

1. Open `output/review.csv` in Excel or Numbers.
2. Check the title, condition, and start price of each card.
3. Type `yes` in the **approve** column for each card to post.
4. Save the file as CSV.

Look hard at cards with `low` confidence.

### Step 3: Post the auctions

```
python -m cardlister post
```

The program writes each eBay link into the review sheet.

### Totals at any time

```
python -m cardlister summary
```

## How the money estimates work

These numbers are rough guesses. Treat them as a starting point only.

- **Quick-sale value.** eBay does not share sold prices with most developers. So the program reads current Buy It Now listings. It skips graded slabs and card lots. It then takes the price at the bottom quarter of the matches. Sellers often ask more than buyers pay, so the low end fits a quick sale better.
- **Store cash estimate.** The program multiplies the quick-sale value by `STORE_CASH_RATE`. The default is 50 percent. Card shops set their own offers, so change this number to match your local shop.
- **Bulk cards.** Cards under `BULK_THRESHOLD` ($3 by default) count as bulk. Each bulk card counts as `BULK_CASH_PER_CARD` ($0.05 by default).

## Limits to know

- **Graded cards.** The program marks graded cards "list by hand". eBay needs extra grading details for slabs.
- **Photo honesty.** Photoroom replaces only the background. It does not repaint the card. eBay requires photos of the real item.
- **Sandbox first.** Keep `EBAY_ENV=sandbox` until test listings look right. Then change it to `production` and run `login` again.

## Running the tests

```
python -m unittest discover -s tests
```
