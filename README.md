# CohesivePacks Card Lister

This program turns iPhone photos of football cards into eBay auctions.

1. You photograph each card: front first, then back.
2. Photoroom's AI turns each photo into a clean studio shot.
3. Claude's AI reads each card's player, year, set, number, and condition.
4. The program looks up current eBay prices for each card.
5. The program estimates a quick-sale value and a store cash value.
6. You check every card in a spreadsheet.
7. The program posts each approved card as a 3-day eBay auction.

## Quick start: scan card values only

The scan finds each card's value. It does not edit photos or post anything to eBay.
It needs only an Anthropic API key, from console.anthropic.com.

1. Install the program (see "Install the program" below).
2. Put `ANTHROPIC_API_KEY=your-key` in a file named `.env` in this folder.
3. Copy all your card photos into the `inbox` folder. Any order works.
4. Run:

```
python -m cardlister scan
```

You can also scan another folder: `python -m cardlister scan "C:\Users\you\Pictures\cards"`.
Try `--limit 3` first to test three cards.

### What the scan does

1. **Reads every photo.** Claude decides whether each photo shows a front or a back. It copies the player, set, year, and number printed on that side.
2. **Groups the photos into cards.** The program matches each front to its back by player, set, and number. When two backs fit, the photo taken closest in time wins. A photo without a match counts as a one-sided card.
3. **Finds sold prices.** Claude searches the web for the card's recent sold prices. It looks at sites like eBay sold listings and 130point. It skips asking prices, card lots, and slabs with a different grade.

### What you get

The program saves `output/values.csv`. You open it in Excel or Numbers. Each row is one card with:

- the card title and details
- the last sale price, its date, and a link to that sale
- the middle price of up to 5 recent sales ("sold_median")
- a store cash estimate

The program also prints the totals for all cards. The scan leaves your photos in place.

### Cost

The scan makes three Claude calls per card plus up to 5 web searches. Check console.anthropic.com for current prices. Test with `--limit 3` and look at your usage page.

### Check the prices

Claude can pick the wrong sale, such as a different parallel. Each sale has a link. Open the link before you trust a high price. The "sale_match" column says "exact", "close", or "none".

## What you need for eBay posting

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

- **Scan.** The `scan` command bases the store cash estimate on the middle of the recent sold prices.
- **Quick-sale value (process command).** eBay does not share sold prices with most developers. So the program reads current Buy It Now listings. It skips graded slabs and card lots. It then takes the price at the bottom quarter of the matches. Sellers often ask more than buyers pay, so the low end fits a quick sale better.
- **Store cash estimate.** The program multiplies the quick-sale value by `STORE_CASH_RATE`. The default is 50 percent. Card shops set their own offers, so change this number to match your local shop.
- **Bulk cards.** Cards under `BULK_THRESHOLD` ($3 by default) count as bulk. Each bulk card counts as `BULK_CASH_PER_CARD` ($0.05 by default).

## Listing a prepared card list

`cards/batch-2026-11-17.csv` already holds all 17 cards from the first batch: titles, details, value estimates, and start prices.

1. Copy the 34 photos from your iPhone into the `inbox` folder. Keep their names, like `IMG_2302`.
2. Run `python -m cardlister import cards/batch-2026-11-17.csv`
3. Check `output/review.csv` and type `yes` in the approve column.
4. Run `python -m cardlister post`

### How start prices work

Each start price covers the store cash value plus eBay's fees (about 13.25% plus $0.40 per order). So any winning bid pays you at least what a card shop would pay in cash. Cheap cards start at $0.99. Shipping is not included, so set your shipping policy to have the buyer pay shipping.

## Limits to know

- **Graded cards.** The program lists PSA, BGS, SGC, CGC, and other slabs with the grader, grade, and certification number. Test one graded card in the sandbox first, because eBay rejects a listing whose grade codes do not match.
- **Photo honesty.** Photoroom replaces only the background. It does not repaint the card. eBay requires photos of the real item.
- **Sandbox first.** Keep `EBAY_ENV=sandbox` until test listings look right. Then change it to `production` and run `login` again.

## Running the tests

```
python -m unittest discover -s tests
```
