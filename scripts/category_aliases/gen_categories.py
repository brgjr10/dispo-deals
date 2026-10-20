"""Generate the consolidated category normalization tables.

One table drives both implementations so they cannot drift:
  * dashboard.html  -> normalizeCategoryMain / normalizeCategorySub (display)
  * utils/categories.py -> CATEGORY_ALIASES / SUBCATEGORY_ALIASES (storage + API)

Keys are compared with spacing/punctuation removed and case ignored, the same
normalisation both sides already use (JS categoryKey == Python category_key).

Run from the project root:

    python scripts/category_aliases/gen_categories.py
    python scripts/category_aliases/apply_py_aliases.py
    python scripts/category_aliases/apply_js_maps.py

tests/test_sidebar.py::TestJsPythonParity then fails if the two tables ever
disagree, so re-running these after editing a table is not optional.
"""

import os
import re

SEP = " \u00b7 "

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The title patterns that rescue a product filed under a catch-all shelf. Kept
# here rather than in utils/categories.py because both tables need to know that
# a mousepad is a dab mat, and this way there is one place to change it.
DAB_MAT_NAME_RE = r"\b(dab\s*-?\s*mats?|dab\s*-?\s*pads?|dabbing\s+mat)\b"

# A mousepad is relocated onto the Dab Mats shelf whatever shelf the store
# filed it under, because the glass and accessory vendors list the silicone
# sheets beside their other stock. Only this spelling is force-moved: "dab
# mat" and "dab pad" already have shelves of their own, and ripping a "Dab Pad"
# out of Concentrates would move a genuine product onto the wrong shelf.
MOUSEPAD_NAME_RE = r"\bmouse\s*-?\s*pads?\b"

# Whole-category relocations. A store sometimes files a shelf under the wrong
# group: bongs and glassware land under Accessories while the Glass group holds
# the rest of them, and the silicone mats turn up both as an Accessories row and
# as a group of their own. Neither the main nor the sub can express that alone,
# because each is individually correct and only the pairing is wrong.
CATEGORY_RELOCATIONS = [
    ("Accessories \u00b7 bongs", "Glass \u00b7 bongs"),
    ("Accessories \u00b7 glassware", "Glass \u00b7 glassware"),
    ("Accessories \u00b7 dab mats", "Dab Mats \u00b7 mats"),
    ("Apparel \u00b7 Hats", "Hats \u00b7 Hats"),
]

# Canonical main categories: JS display name -> Python canonical name.
# They differ only where the historical JS map pluralised and Python did not.
MAIN_CANON = {
    "Apparel": "Apparel",
    "Hats": "Hats",
    "Beanies": "Beanies",
    "Bags": "Bags",
    "Footwear": "Footwear",
    "Accessories": "Accessories",
    "Concentrates": "Concentrate",
    "Edible": "Edible",
    "Flower": "Flower",
    "Vaporizers": "Vaporizers",
    "Pre-Rolls": "Pre-Rolls",
    "Tinctures": "Tincture",
    "Topicals": "Topicals",
    "Oral": "Oral",
    "Glass": "Glass",
    "Puffco": "Puffco",
    "Kits": "Kits",
    "Merch": "Merch",
    "Misc": "Misc",
    "Skate": "Skate",
    "Dab Mats": "Dab Mats",
    "Gift Cards": "Gift Cards",
    "Knitwear": "Knitwear",
}


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


# ---------------------------------------------------------------------------
# MAIN CATEGORY ALIASES: (js canonical, python canonical, [raw spellings])
# ---------------------------------------------------------------------------
MAINS = [
    # ---- Apparel -----------------------------------------------------------
    ("Apparel", "Apparel", [
        "Apparel", "APPAREL", "Active", "Ankle Socks",
        "Bell Bottoms", "bell bottoms", "Belt", "belt", "Belts",
        "Belts & Harnesses", "Handmade Belts", "Bikini", "bikini",
        "Blazer", "blazer", "Blouse", "blouse", "Bodycon", "bodycon",
        "Bodysuit", "bodysuit", "Bolero", "Boxers", "boxers", "Bralet",
        "bralet", "Cardigan", "cardigan", "Cardigans", "Cloak", "cloak",
        "Clothing", "clothing", "Clothing (Dropship)", "Coats", "coat",
        "Corset", "corset", "Corsets", "CORSET", "CORSETS", "Costumes",
        "Crop Top", "crop top", "Denim", "Dresses", "Duster", "duster",
        "Flares", "flares", "Gloves", "gloves", "Harness", "harness",
        "Harnesses", "Hats/Scarves/Gloves", "Hoodies/Sweats", "Jogger Shorts",
        "Jumpsuit", "jumpsuit", "Jumpsuits", "Jumpsuits & Rompers",
        "Jumpsuits/Playsuits", "Kids", "Knit Dress", "knit dress", "Kuties",
        "kuties", "Leg Warmers", "leg warmers", "Leggings", "leggings",
        "Lingerie", "Lingerie & Sleepwear", "Long Sleeve", "long sleeve",
        "Longsleeve", "Long Socks", "long socks", "MAXI", "Maxi", "maxi",
        "Mens Black Style_T-Shirt", "Mens Indigo Style_T-Shirt",
        "Mens Military_green Style_T-Shirt", "MIDI", "Midi", "midi",
        "MINI", "Mini", "mini", "Outerwear", "outerwear", "Pants", "pants",
        "Panty", "panty", "Pasties & Tatts", "Playsuit", "playsuit", "Rompers",
        "Sarong", "Scarf", "scarves", "Scarves & Gloves", "Scarf Slides",
        "Shirts/Blouses",
        "Short Sleeve", "short sleeve", "Skirt", "skirt", "Skirts", "Socks",
        "socks", "Socks & Tights", "Standard Tee", "Stockings",
        "Sweater", "sweater", "Sweaters", "Sweater Dress", "sweater dress",
        "Sweatpants", "Sweats", "sweats", "Sweatshirt", "sweatshirt",
        "Swim", "Swimsuit", "swimsuit", "T Shirt", "T shirt", "t shirt",
        "Tank", "tank", "Tees", "tees", "T-Shirt", "T-Shirts", "tshirts",
        "Tights", "tights", "TOPS", "Tops", "Trunks", "Trousers", "trousers",
        "Trousers/Shorts", "Tunic", "tunic", "Veil", "Vest", "vest",
        "Vtg Tops", "Wide Leg", "wide leg", "Womens Black Style_T-Shirt",
        "Womens Heather_grey Style_T-Shirt",
        # Wholesale apparel taxonomy codes, kept working as before.
        "TEE SS PRINTED", "TEE LS PRINTED", "Tee", "KNIT SS TOP", "KNIT LS TOP",
        "KNIT TANK CUT/ SEW", "WOVEN SS TOP", "WOVEN LS TOP",
        "Crewneck Fleece Printed", "Crewneck Printed Fleece",
        "Hoody Fleece Printed", "Hoodie", "Hoodies", "HOODED FLEECE CUT/ SEW",
        "HOODED FLEECE CUT/SEW", "OUTERWEAR JACKET CUT/SEW",
        "OUTERWEAR WINDBREAKER CUT/ SEW", "OUTERWEAR WINDBREAKER CUT/SEW",
        "Jackets", "Jacket", "jacket", "Shorts", "BOTTOM KNIT PANT",
        "BOTTOM KNIT SHORT",
        "BOTTOM PRINTED PANT", "BOTTOM PRINTED SHORT", "BOTTOM SWIM TRUNK",
        "BOTTOM WINDBREAKER PANT", "BOTTOM WOVEN PANT", "Shirts", "Shirt",
        "shirt", "Bottoms", "Jersey",
    ]),

    # ---- Headwear ----------------------------------------------------------
    ("Hats", "Hats", [
        "ACC DAD HAT", "ACC SNAPBACK", "ACC SNAPBACK HAT", "ACC TRUCKER HAT",
        "Cap Bundle", "Caps", "Fedora", "Handmade Hats", "Hat", "hat",
        "Hats", "hats", "Headwear",
    ]),
    ("Beanies", "Beanies", [
        "Acc Knit Beanie", "Beanie", "beanie", "Beanies", "Toque",
    ]),

    # ---- Bags --------------------------------------------------------------
    ("Bags", "Bags", [
        "Acc Shoulder Bag", "Acc Woven Backpack", "Backpack", "backpack",
        "Bags", "bags", "Bags & Wallets", "Coin Purse", "Cross Body",
        "cross body", "Duffle", "duffle", "HANDBAGS", "Handbag", "handbag",
        "Handbags", "Luggage", "Messenger", "Tote", "Tote Bag", "Weekend Bag",
        "Wallet", "wallet",
    ]),

    # ---- Footwear ----------------------------------------------------------
    ("Footwear", "Footwear", [
        "Acc Footwear", "Boots", "boots", "Boots & Booties", "Creepers",
        "creepers", "Flats", "flats", "Flip Flop", "Footwear", "footwear",
        "Heels", "heels", "Platform Boots", "platform boots", "Platforms",
        "Sandal", "sandal", "Sandals", "Shoes", "Sneakers",
        "Wedges",
    ]),

    # ---- Accessories -------------------------------------------------------
    ("Accessories", "Accessories", [
        "Acc Miscellaneous", "Accesory", "Accessories", "Adapters",
        "Atomizer", "Beads", "Blunt Tips", "Bob Marley", "Bowl Piece",
        "Cannabutter Maker", "Case", "Chill Straw", "Chillum",
        "Cleaning Products", "Clear Solid Pipes", "Container",
        "Dabbing Accessories", "Deals - Dry Pipes", "Dry Herb Pipe",
        "Dry Pipe", "Dugout", "earrings", "Earrings", "Electric Pipe",
        "Electronic Dab Tool", "encalmo disc ash catchers", "Gas Mask",
        "Glass Pipe", "Glycerine Straw", "Hair Accessories", "Hair Accessory",
        "hair accessory", "Hand Pipe", "Hand pipe", "Handpipe", "handpipes",
        "Jars", "Jewelry", "Keychain", "keychain", "Lanyard",
        "Lighter 3-Pack", "Lighter Holder", "Marbles", "Mystery Marble",
        "Necklace",         "necklace", "Necklaces", "Necklaces/Chokers", "Opal Spheres",
        "Scrunchie", "scrunchie", "Sherlock Pipe",
        "Silicone Accessory Kit", "Smoking Accessories", "Smoking pipe",
        "Smoke Miscellaneous", "Solid Pipes", "Spoon Pipe", "Sunglasses",
        "sunglasses", "Terp Jars", "Terp Pillar", "Terp Timer", "Tether",
        "tether", "The Dopest Battery", "Vape Accessory",
        "Vaporizer Accessories", "Wholesale Accessories", "Zippo",
        "Saber Accessory", "Bracelet", "bracelet", "Choker", "choker",
        # Long-standing aliases that already pointed here.
        "Accessory", "Character", "Batteries", "Battery", "Charger", "Chargers",
        "Coil", "Coils", "Grinder", "Grinders", "Lighter", "Lighters",
        "Lighter Case", "Lighter Cases", "Tray", "Trays", "Rolling Tray",
        "Rolling Trays", "Storage", "Cleaning", "Cleaning & Care",
        "Cleaning Supplies", "Cleaning Supply", "Cleaning Care",
        "Replacement Part", "Replacement Parts", "Joint Case", "Joint Cases",
        "Joint Holder", "Joint Holders", "Rolling Papers", "Rolling Paper",
        "Cones", "Cone", "Rolling Cones", "Rolling Cones Accessories",
        "Ashtray", "Ashtrays", "Dab Accessories", "Dab Accessory",
        "Dab Tools", "Dab Tool", "Tools", "Tool",
        "Protection", "Pearl", "Pearls", "Glassware",
    ]),

    # ---- Cannabis: concentrates -------------------------------------------
    ("Concentrates", "Concentrate", [
        "Banger Basket", "Concentrate", "Concentrates", "Ice Guys Hash",
        "Liquid Diamonds", "2g liquid diamonds", "liquid diamonds",
        "Nectar Collector", "Quartz Banger", "Slurper Caps", "static hash",
        "Thca Diamonds",
        # Long-standing aliases that already pointed here.
        "Extract", "Extracts", "Hash", "Banger", "Bangers", "Carb", "Carb Cap",
        "Carb Caps", "Nail", "Nails", "Quartz", "Terp Slurper", "Terp Slurpers",
        "Terp Pearl", "Terp Pearls", "Dab Rig", "Dab Rigs", "Oil Rig",
        "Oil Rigs", "Concentrate Rig", "Concentrate Rigs",
        "Concentrate Accessories", "Concentrate Accessory",
    ]),

    # ---- Cannabis: edibles -------------------------------------------------
    ("Edible", "Edible", [
        "Beverage", "Edible", "Edibles", "Gummy Sharks", "Syrup",
        "syrup builder 3 for $60", "The Dopest Cubes gummies",
    ]),

    # ---- Cannabis: flower --------------------------------------------------
    ("Flower", "Flower", [
        "$55 smalls ounce", "14 grams cheap", "14 grams smalls",
        "14g smalls 2 pack (2 7g packs)", "2-pack smalls 1 ounce",
        "3.5g dep flower pack", "7 grams premium flower",
        "Build your own BIGs premium ounce", "Flower", "Flowers",
        "Flower Variety pack PREMIUM", "Indoor Flower", "Premium Dep Flower",
        "Premium Dep Flower $95 ounce", "QP smalls variety pack",
    ]),

    # ---- Cannabis: vaporizers ---------------------------------------------
    ("Vaporizers", "Vaporizers", [
        "1.5g vape cartridge", "1g THCA cartridge", "2g Dual flavor disposable",
        "mystery 1g disposable", "pumkin pie cart and battery",
        "Vape Cartridge", "Vape Disposable", "Vape cartridge",
        "vape cartridge", "Vaporizers",
        # Long-standing aliases that already pointed here.
        "Vapes", "Vape", "Vaporizer", "Carts", "Cartridges", "E-Rig",
        "E-Rigs", "E-Rigs Vaporizers", "Electronic Rig", "Electronic Rigs",
    ]),

    # ---- Cannabis: pre-rolls / tinctures / topicals ------------------------
    ("Pre-Rolls", "Pre-Rolls", [
        "Pre-Roll", "Pre-Rolls", "Preroll", "Prerolls",
    ]),
    ("Tinctures", "Tincture", ["Tincture", "Tinctures"]),
    ("Topicals", "Topicals", ["Topical", "Topicals"]),
    ("Oral", "Oral", ["Oral"]),

    # ---- Glass -------------------------------------------------------------
    ("Glass", "Glass", [
        "45mm beakers", "45mm mini collins beakers", "5mm beakers",
        "5mm straights", "7mm beakers", "7mm mini beaker",
        "7mm scoped mini beaker", "9mm beakers", "Beaker", "beakers",
        "Blunt Bubbler", "bubbler danklins", "Bongs & Dab Rigs",
        "Clear Models", "Clear Models (2nd)", "Clear Slides", "Color Models",
        "collins beakers", "danklin coil", "downstems", "Electric Bong",
        "frosted beakers", "frosted signature straights",
        "full color premium signature beakers", "full color scoped beakers",
        "full color signature", "full size", "Glass", "Glass Attachment",
        "Glass Bong", "Glass Bubbler", "Glass Rig", "Glass Water Pipe",
        "glass accessories", "glass top", "Gravity Infuser", "Gravity Pipe",
        "Hammers", "Heady Glass", "heavy hit beakers",
        "Hologram Toro", "illadelph coils", "illadelph straight tubes",
        "illadelph tubes", "Percolator", "premium series",
        "Prism Halo Fam Favorites", "scoped series", "Steam Roller",
        "Steamroller", "Toro", "Waterpipes & Rigs", "Wholesale Models",
        # Long-standing aliases that already pointed here.
        "Bong", "Bongs", "Rig", "Rigs", "Bubbler", "Bubblers",
        "Ash Catcher", "Ash Catchers", "Bowl", "Bowls", "Pipe", "Pipes",
        "Flower Pipe", "Flower Pipes", "Flower Pipes and Accessories",
        "Mouthpiece", "Mouthpieces", "Water Pipe", "Water Pipes",
        "Joint Bubbler", "Joint Bubblers", "Slide", "Slides", "Pendant",
        "Pendants", "Ohio Glassblowers Show 2025", "Ohio Glassblowers Show",
        "Steve Sizelove Drop 2025", "Steve Sizelove Drop",
    ]),

    # ---- Puffco ------------------------------------------------------------
    ("Puffco", "Puffco", [
        "Modül", "Modül Accessories", "Official Puffco", "Peak Attachment",
        "Proxy Core", "Puffco", "Puffco Accessories", "Puffco Attachments",
        "Puffco Charms", "Puffco Dry Tops", "Puffco Joysticks",
        "Puffco Pivot Mouthpieces", "Puffco Proxy Attachments",
        # Long-standing aliases that already pointed here.
        "Peak", "Peak Pro", "Peak Accessories", "Peak Pro Accessories",
        "Pivot", "Pivot Accessories", "Pivot Accessory", "Proxy Accessory",
        "Proxy Core Accessory",
    ]),

    # ---- Kits / merch / skate / misc --------------------------------------
    ("Kits", "Kits", ["Kits", "Kit", "Smart Rig Kit", "Smoking Kit"]),
    ("Merch", "Merch", ["Merch", "Merchandise", "Box Stickers",
                        "Die Cut Stickers", "Sticker Pack", "Patches",
                        "Pin", "Pinback Buttons", "Posters"]),
    ("Skate", "Skate", ["Deck", "Skate", "Skateboard Deck", "Skater", "skater"]),
    ("Dab Mats", "Dab Mats", [
        "Dab Mat", "Dab Mats", "Dabbing Mat", "Hex Mat", "Mat", "Mats",
        "Dab Pad", "Dab Pads", "Mousepad", "Mousepads", "Mouse Pad",
        "Mouse Pads",
    ]),
    ("Gift Cards", "Gift Cards", ["Gift Card", "Gift Cards"]),
    ("Knitwear", "Knitwear", ["Knitwear", "Knits"]),

    # Everything below is not a product shelf: sale flags, junk placeholders,
    # home goods and services. They collapse onto Misc so the sidebar shows one
    # catch-all row instead of dozens of one-item groups.
    ("Misc", "Misc", [
        "2pc set", "Archives Sale", "Assurance", "Bedding", "Blankets",
        "blanket", "Blowout",
        "blowout", "Bundle", "bundle", "Bundle Set", "Canvas", "Car Styling",
        "Clearance", "clearance", "Coasters", "Collabs", "collabs",
        "Current Custom Drop", "current custom drop", "Current Drops",
        "current drops", "Cup", "cup", "Daily Deals", "Deals", "Deals - Gear",
        "Decor", "Direct Sale", "Donation", "Drinkware", "Elite",
        "Essentials $99 Subscription Pack", "Expivi Product Replica",
        "Extras Sale", "Extensions", "extensions", "Eyeliner", "Eyes",
        "Eyeshadow", "Face & Body", "Fun & Games", "Gift With Purchase",
        "H", "Hair", "Heavyweight $175 Subscription Pack",
        "Highlight section", "Home Stuff", "Home accessory", "home accessory",
        "Homeware", "Ice Pack for shipping", "Incense", "Inflatable",
        "Insurance", "Juicy J Collab", "juicy j collab", "Kitchen & Bar",
        "Lights", "Lip Liner", "lip product", "Lips", "Lipstick",
        "Membership", "membership", "Mirrors", "Misc", "Mothership Meltdown",
        "Mug", "mug", "New Products", "Other", "Other Shit", "Outdoor",
        "Pallets", "pallets", "Pomade", "pomade", "Product", "product",
        "Rug", "rug", "Shipping Protection", "Sign", "sign",
        "Springsale", "springsale", "Subscription box", "Tableware",
        "tableware", "Tarot Cards", "tarot cards", "Towel", "towel",
        "Toy", "toy", "Umbrella", "Uncategorized", "Vase", "Wallpaper",
        "Warranty", "warranty",
    ]),
]

# ---------------------------------------------------------------------------
# SUBCATEGORY ALIASES: (js main, py main, canonical label, [raw spellings])
# ---------------------------------------------------------------------------
SUBS = [
    # ---- Apparel -----------------------------------------------------------
    # A short-sleeve printed tee is a t-shirt, so the wholesale codes and the
    # "Short Sleeve Tee" label fold into that row rather than standing alone.
    ("Apparel", "Apparel", "T-Shirts", ["TEE SS PRINTED"]),
    ("Apparel", "Apparel", "Short Sleeve Knit Top", ["KNIT SS TOP"]),
    ("Apparel", "Apparel", "Long Sleeve Knit Top", ["KNIT LS TOP"]),
    ("Apparel", "Apparel", "Knit Tank", ["KNIT TANK CUT/ SEW", "KNIT TANK CUT/SEW"]),
    ("Apparel", "Apparel", "Short Sleeve Woven Top", ["WOVEN SS TOP"]),
    ("Apparel", "Apparel", "Long Sleeve Woven Top", ["WOVEN LS TOP"]),
    ("Apparel", "Apparel", "Hooded Fleece", [
        "HOODED FLEECE CUT/ SEW", "HOODED FLEECE CUT/SEW", "Hoody Fleece Printed",
    ]),
    ("Apparel", "Apparel", "Jacket", ["OUTERWEAR JACKET CUT/SEW"]),
    ("Apparel", "Apparel", "Windbreaker", [
        "OUTERWEAR WINDBREAKER CUT/SEW", "OUTERWEAR WINDBREAKER CUT/ SEW",
    ]),
    ("Apparel", "Apparel", "Knit Pants", ["BOTTOM KNIT PANT"]),
    ("Apparel", "Apparel", "Knit Shorts", ["BOTTOM KNIT SHORT"]),
    ("Apparel", "Apparel", "Printed Pants", ["BOTTOM PRINTED PANT"]),
    ("Apparel", "Apparel", "Printed Shorts", ["BOTTOM PRINTED SHORT"]),
    ("Apparel", "Apparel", "Swim Trunks", ["BOTTOM SWIM TRUNK"]),
    ("Apparel", "Apparel", "Windbreaker Pants", ["BOTTOM WINDBREAKER PANT"]),
    ("Apparel", "Apparel", "Woven Pants", ["BOTTOM WOVEN PANT"]),
    ("Apparel", "Apparel", "Crewneck Fleece", [
        "Crewneck Fleece Printed", "Crewneck Printed Fleece",
    ]),
    ("Apparel", "Apparel", "Hoodies", ["Hoodie", "Hoodies"]),
    ("Apparel", "Apparel", "T-Shirts", ["Tee", "Tees", "tees", "T-Shirt",
                                        "T-Shirts", "T Shirt", "T shirt",
                                        "t shirt", "tshirts", "Standard Tee",
                                        "Short Sleeve Tee", "Long Sleeve Tee",
                                        "TEE SS PRINTED", "TEE LS PRINTED"]),
    ("Apparel", "Apparel", "Shirts", ["Shirt", "shirts", "Shirts",
                                      "Shirts/Blouses"]),
    ("Apparel", "Apparel", "Blouses", ["Blouse", "blouse"]),
    # A "long sleeve" row is a top; the three spellings of it split the shelf.
    ("Apparel", "Apparel", "Tops", ["Tops", "TOPS", "Vtg Tops", "Tank",
                                    "tank", "Tunic", "tunic", "long sleeve",
                                    "Long Sleeve", "longsleeve",
                                    "short sleeve", "Short Sleeve"]),
    ("Apparel", "Apparel", "Activewear", ["Active"]),
    ("Apparel", "Apparel", "Socks", ["Socks", "socks", "Long Socks", "long socks"]),
    ("Apparel", "Apparel", "Ankle Socks", ["Ankle Socks"]),
    ("Apparel", "Apparel", "Socks & Tights", ["Socks & Tights"]),
    ("Apparel", "Apparel", "Tights", ["Tights", "tights", "Stockings"]),
    ("Apparel", "Apparel", "Jersey", ["Jersey", "jersey"]),
    ("Apparel", "Apparel", "Pants", ["Pants", "pants", "Denim", "Sweatpants",
                                     "Wide Leg", "wide leg"]),
    ("Apparel", "Apparel", "Trousers", ["Trousers", "trousers", "Trousers/Shorts"]),
    ("Apparel", "Apparel", "Shorts", ["Shorts", "shorts", "Jogger Shorts"]),
    ("Apparel", "Apparel", "Skirts", ["Skirt", "skirt", "Skirts"]),
    ("Apparel", "Apparel", "Jackets", ["Jackets", "Jacket", "jacket", "Blazer",
                                       "blazer", "Bolero"]),
    ("Apparel", "Apparel", "Coats", ["Coats", "coat", "Cloak", "cloak",
                                     "Duster", "duster"]),
    ("Apparel", "Apparel", "Outerwear", ["Outerwear", "outerwear"]),
    ("Apparel", "Apparel", "Sweaters", ["Sweater", "sweater", "Sweaters",
                                        "Sweatshirt", "sweatshirt", "Sweats",
                                        "sweats", "Hoodies/Sweats"]),
    ("Apparel", "Apparel", "Cardigans", ["Cardigan", "cardigan", "Cardigans"]),
    ("Apparel", "Apparel", "Knit Dress", ["Knit Dress", "knit dress",
                                          "Sweater Dress", "sweater dress"]),
    ("Apparel", "Apparel", "Boxers", ["Boxers", "boxers"]),
    ("Apparel", "Apparel", "Belts", ["Belt", "belt", "Belts", "Belts & Harnesses",
                                     "Handmade Belts", "Harness", "harness",
                                     "Harnesses"]),
    ("Apparel", "Apparel", "Dresses", ["Dresses", "Maxi", "maxi", "MAXI",
                                       "Midi", "midi", "MIDI", "Mini", "mini",
                                       "MINI"]),
    ("Apparel", "Apparel", "Corsets", ["Corset", "corset", "Corsets", "CORSET",
                                       "CORSETS", "Bodycon", "bodycon"]),
    ("Apparel", "Apparel", "Crop Tops", ["Crop Top", "crop top"]),
    ("Apparel", "Apparel", "Leggings", ["Leggings", "leggings"]),
    ("Apparel", "Apparel", "Leg Warmers", ["Leg Warmers", "leg warmers"]),
    ("Apparel", "Apparel", "Lingerie", ["Lingerie", "Lingerie & Sleepwear",
                                        "Bralet", "bralet", "Panty", "panty",
                                        "Pasties & Tatts"]),
    ("Apparel", "Apparel", "Bodysuits", ["Bodysuit", "bodysuit"]),
    ("Apparel", "Apparel", "Jumpsuits", ["Jumpsuit", "jumpsuit", "Jumpsuits",
                                         "Jumpsuits & Rompers",
                                         "Jumpsuits/Playsuits", "Playsuit",
                                         "playsuit", "Rompers"]),
    ("Apparel", "Apparel", "Flared Pants", ["Flares", "flares", "Bell Bottoms",
                                            "bell bottoms"]),
    ("Apparel", "Apparel", "Costumes", ["Costumes"]),
    ("Apparel", "Apparel", "Swim", ["Swim", "Swimsuit", "swimsuit", "Bikini",
                                    "bikini", "Trunks", "Sarong"]),
    ("Apparel", "Apparel", "Vests", ["Vest", "vest"]),
    ("Apparel", "Apparel", "Clothing", ["Clothing", "clothing",
                                        "Clothing (Dropship)", "APPAREL"]),
    ("Apparel", "Apparel", "Veil", ["Veil"]),
    # A scarf slide is a scarf, not footwear: the stores sell them beside the
    # scarves and the name only shares a word with sandals.
    ("Apparel", "Apparel", "Scarves & Gloves", ["Scarves & Gloves", "Scarf",
                                                "Scarf Slides", "Scarf Slide",
                                                "Gloves", "gloves",
                                                "Hats/Scarves/Gloves"]),
    ("Apparel", "Apparel", "Kids", ["Kids", "Kuties", "kuties"]),
    ("Apparel", "Apparel", "Sets", ["Mens Black Style_T-Shirt",
                                    "Mens Indigo Style_T-Shirt",
                                    "Mens Military_green Style_T-Shirt",
                                    "Womens Black Style_T-Shirt",
                                    "Womens Heather_grey Style_T-Shirt"]),

    # ---- Headwear ----------------------------------------------------------
    ("Hats", "Hats", "Snapback Hats", ["ACC SNAPBACK HAT"]),
    ("Hats", "Hats", "Snapbacks", ["ACC SNAPBACK"]),
    ("Hats", "Hats", "Trucker Hats", ["ACC TRUCKER HAT"]),
    ("Hats", "Hats", "Dad Hat", ["ACC DAD HAT"]),
    ("Hats", "Hats", "Headwear", ["Headwear", "headwear", "Cap Bundle",
                                  "Fedora", "Caps", "Handmade Hats"]),
    ("Hats", "Hats", "Hats", ["Hat", "hat", "Hats", "hats"]),
    ("Beanies", "Beanies", "Knit Beanie", ["Acc Knit Beanie"]),
    ("Beanies", "Beanies", "Beanies", ["Beanie", "beanie", "Beanies",
                                       "Toque"]),

    # ---- Bags --------------------------------------------------------------
    ("Bags", "Bags", "Shoulder Bags", ["Acc Shoulder Bag"]),
    ("Bags", "Bags", "Woven Backpacks", ["Acc Woven Backpack"]),
    ("Bags", "Bags", "Backpacks", ["Backpack", "backpack"]),
    ("Bags", "Bags", "Handbags", ["Handbag", "handbag", "Handbags",
                                  "HANDBAGS"]),
    ("Bags", "Bags", "Totes", ["Tote", "Tote Bag"]),
    ("Bags", "Bags", "Wallets", ["Wallet", "wallet", "Bags & Wallets"]),
    ("Bags", "Bags", "Coin Purses", ["Coin Purse"]),
    ("Bags", "Bags", "Weekend Bags", ["Weekend Bag"]),
    ("Bags", "Bags", "Messenger Bags", ["Messenger"]),
    ("Bags", "Bags", "Duffles", ["Duffle", "duffle"]),
    ("Bags", "Bags", "Cross Body", ["Cross Body", "cross body"]),
    ("Bags", "Bags", "Luggage", ["Luggage"]),
    ("Bags", "Bags", "Bags", ["Bags", "bags"]),

    # ---- Footwear ----------------------------------------------------------
    ("Footwear", "Footwear", "Footwear", ["Acc Footwear", "Footwear",
                                          "footwear", "Shoes", "Sneakers"]),
    ("Footwear", "Footwear", "Boots", ["Boots", "boots", "Boots & Booties",
                                       "Platform Boots", "platform boots"]),
    ("Footwear", "Footwear", "Creepers", ["Creepers", "creepers"]),
    ("Footwear", "Footwear", "Heels", ["Heels", "heels", "Wedges"]),
    ("Footwear", "Footwear", "Platforms", ["Platforms"]),
    ("Footwear", "Footwear", "Flats", ["Flats", "flats"]),
    ("Footwear", "Footwear", "Sandals", ["Sandals", "Sandal", "sandal"]),
    ("Footwear", "Footwear", "Slides", ["Flip Flop"]),

    # ---- Accessories -------------------------------------------------------
    ("Accessories", "Accessories", "batteries", ["batteries"]),
    ("Accessories", "Accessories", "pearls", ["pearls"]),
    ("Accessories", "Accessories", "cones", ["cones"]),
    ("Accessories", "Accessories", "pipes", ["pipes"]),
    ("Accessories", "Accessories", "grinders", ["grinders"]),
    # A mousepad is the same product: the stores list silicone sheets beside
    # desk mats, and "Mousepad" is its own shelf at more than one of them.
    ("Accessories", "Accessories", "dab mats", [
        "dab mats", "Mousepad", "Mousepads", "Mouse Pad", "Mouse Pads",
    ]),
    # Same label as the Accessories row above so the dashboard's flat sub map
    # resolves "mousepad" to one spelling whichever group it came from.
    ("Dab Mats", "Dab Mats", "dab mats", [
        "Mousepad", "Mousepads", "Mouse Pad", "Mouse Pads",
    ]),
    ("Accessories", "Accessories", "papers & rolling supplies",
     ["papers & rolling supplies"]),
    ("Accessories", "Accessories", "glassware", ["glassware"]),
    ("Accessories", "Accessories", "bowls", ["bowls", "Bowl Piece"]),
    ("Accessories", "Accessories", "rolling trays", ["rolling trays",
                                                     "Preparation Tray"]),
    ("Accessories", "Accessories", "lighters", ["lighters", "Zippo",
                                                "Lighter 3-Pack",
                                                "Lighter Holder"]),
    ("Accessories", "Accessories", "devices", ["devices"]),
    ("Accessories", "Accessories", "mouthpieces", ["mouthpieces"]),
    ("Accessories", "Accessories", "ashtrays", ["ashtrays"]),
    ("Accessories", "Accessories", "joint cases", ["joint cases"]),
    ("Accessories", "Accessories", "ash catchers", ["ash catchers",
                                                    "encalmo disc ash catchers"]),
    ("Accessories", "Accessories", "dab tools", ["dab tools",
                                                 "Electronic Dab Tool",
                                                 "Terp Pillar", "Terp Timer"]),
    ("Accessories", "Accessories", "tools", ["tools"]),
    ("Accessories", "Accessories", "trays", ["trays"]),
    ("Accessories", "Accessories", "cleaning solutions",
     ["cleaning-solutions", "Cleaning Products"]),
    ("Accessories", "Accessories", "joint holders", ["joint holders"]),
    ("Accessories", "Accessories", "eyewear", ["Sunglasses", "sunglasses"]),
    ("Accessories", "Accessories", "dugouts", ["Dugout"]),
    ("Accessories", "Accessories", "smoking accessories",
     ["Smoking Accessories", "Bob Marley", "Gas Mask"]),
    ("Accessories", "Accessories", "miscellaneous", ["Acc Miscellaneous",
                                                     "Smoke Miscellaneous",
                                                     "Accesory", "Keychain",
                                                     "keychain", "Lanyard"]),
    ("Accessories", "Accessories", "chargers", ["chargers"]),
    ("Accessories", "Accessories", "rolling papers", ["rolling papers"]),
    ("Accessories", "Accessories", "protection", ["protection"]),
    ("Accessories", "Accessories", "bongs", ["Bong"]),
    # Accessories rows are lowercase throughout, so these follow the shelf.
    ("Accessories", "Accessories", "chillum", ["Chillum"]),
    ("Accessories", "Accessories", "dab straws", ["Dab Straw", "Dab Straws",
                                                  "Glycerine Straw"]),
    ("Accessories", "Accessories", "glass tips", ["Glass Tip", "Glass Tips"]),
    ("Accessories", "Accessories", "rolling machine", ["Rolling Machine",
                                                       "Rolling Machines"]),
    ("Accessories", "Accessories", "lighter cases", ["lighter cases",
                                                     "Lighter Cases"]),
    ("Accessories", "Accessories", "screens", ["Screens"]),
    ("Accessories", "Accessories", "tips", ["Tips"]),
    ("Accessories", "Accessories", "wraps", ["Wraps"]),
    ("Accessories", "Accessories", "storage", ["storage-containers", "Jars",
                                               "Container", "Case",
                                               "Terp Jars"]),
    ("Accessories", "Accessories", "lighter cases", ["lighter cases",
                                                     "Lighter Cases"]),
    ("Accessories", "Accessories", "jewelry", ["Jewelry", "Necklaces",
                                               "Necklace", "necklace",
                                               "Necklaces/Chokers", "Earrings",
                                               "earrings", "Beads", "Marbles",
                                               "Mystery Marble",
                                               "Opal Spheres"]),
    ("Accessories", "Accessories", "blunt supplies", ["Blunt Tips"]),
    ("Accessories", "Accessories", "adapters", ["Adapters"]),
    ("Accessories", "Accessories", "batteries & atomizers", ["Atomizer"]),
    ("Accessories", "Accessories", "pipe accessories", ["Dry Pipe",
                                                        "Hand Pipe",
                                                        "Hand pipe",
                                                        "Handpipe",
                                                        "handpipes",
                                                        "Smoking pipe",
                                                        "Spoon Pipe",
                                                        "Sherlock Pipe",
                                                        "Dry Herb Pipe",
                                                        "Glass Pipe",
                                                        "Clear Solid Pipes",
                                                        "Solid Pipes",
                                                        "Deals - Dry Pipes",
                                                        "Electric Pipe",
                                                        "Chill Straw"]),
    ("Accessories", "Accessories", "smoking accessories",
     ["Smoking Accessories", "Bob Marley", "Gas Mask"]),
    ("Accessories", "Accessories", "vape accessories",
     ["Vape Accessory", "Vaporizer Accessories", "The Dopest Battery"]),
    ("Accessories", "Accessories", "silicone accessories",
     ["Silicone Accessory Kit", "Cannabutter Maker"]),
    ("Accessories", "Accessories", "hair accessories",
     ["Hair Accessories", "Hair Accessory", "hair accessory", "Scrunchie",
      "scrunchie"]),
    ("Accessories", "Accessories", "tethers", ["Tether", "tether"]),
    ("Accessories", "Accessories", "wholesale accessories",
     ["Wholesale Accessories", "Dabbing Accessories"]),

    # ---- Concentrates ------------------------------------------------------
    ("Concentrates", "Concentrate", "live resin", ["live resin", "Resin"]),
    ("Concentrates", "Concentrate", "shatter", ["shatter"]),
    ("Concentrates", "Concentrate", "live rosin", ["live rosin"]),
    ("Concentrates", "Concentrate", "rosin", ["rosin"]),
    ("Concentrates", "Concentrate", "badder", ["badder"]),
    ("Concentrates", "Concentrate", "sugar", ["sugar", "Terp Sugar"]),
    ("Concentrates", "Concentrate", "budder", ["budder"]),
    ("Concentrates", "Concentrate", "rso", ["rso"]),
    ("Concentrates", "Concentrate", "applicators", ["applicators",
                                                    "Syringe"]),
    ("Concentrates", "Concentrate", "crumble", ["crumble"]),
    ("Concentrates", "Concentrate", "oil", ["concentrates-oil"]),
    ("Concentrates", "Concentrate", "infused-flower", ["infused-flower"]),
    ("Concentrates", "Concentrate", "ground flower", ["Ground Flower"]),
    ("Concentrates", "Concentrate", "sauce", ["sauce"]),
    ("Concentrates", "Concentrate", "wax", ["wax"]),
    ("Concentrates", "Concentrate", "hash", ["hash", "Ice Guys Hash",
                                             "static hash"]),
    ("Concentrates", "Concentrate", "moonrocks", ["Moonrocks"]),
    ("Concentrates", "Concentrate", "diamonds", ["Liquid Diamonds",
                                                 "2g liquid diamonds",
                                                 "liquid diamonds",
                                                 "Thca Diamonds"]),
    ("Concentrates", "Concentrate", "quartz", ["Quartz Banger",
                                               "Banger Basket",
                                               "Slurper Caps",
                                               "Nectar Collector"]),

    # ---- Edibles -----------------------------------------------------------
    ("Edible", "Edible", "gummies", ["gummies", "Gummy Sharks",
                                     "The Dopest Cubes gummies"]),
    ("Edible", "Edible", "chocolates", ["chocolates"]),
    ("Edible", "Edible", "drinks", ["drinks", "Seltzer", "Beverage"]),
    ("Edible", "Edible", "live rosin gummies", ["live rosin gummies"]),
    ("Edible", "Edible", "capsules & tablets", ["capsules & tablets"]),
    ("Edible", "Edible", "chews", ["chews"]),
    ("Edible", "Edible", "hard candy", ["hard candy"]),
    ("Edible", "Edible", "live resin gummies", ["live resin gummies"]),
    ("Edible", "Edible", "Edible", ["Edible"]),
    ("Edible", "Edible", "bars", ["Bar"]),
    ("Edible", "Edible", "candy", ["candy", "Caramel"]),
    ("Edible", "Edible", "mints", ["mints"]),
    ("Edible", "Edible", "dissolvables", ["dissolvables"]),
    ("Edible", "Edible", "cooking & baking", ["cooking-baking"]),
    ("Edible", "Edible", "syrups", ["Syrup", "syrup builder 3 for $60"]),

    # ---- Flower ------------------------------------------------------------
    ("Flower", "Flower", "whole flower", ["whole flower"]),
    ("Flower", "Flower", "small buds", ["small buds", "Smalls", "Mini Buds",
                                        "Budlets"]),
    ("Flower", "Flower", "premium", ["premium", "7 grams premium flower",
                                     "Premium Dep Flower",
                                     "Premium Dep Flower $95 ounce",
                                     "Flower Variety pack PREMIUM"]),
    ("Flower", "Flower", "popcorn", ["Popcorn", "smalls-popcorn"]),
    ("Flower", "Flower", "indoor flower", ["Indoor Flower"]),
    ("Flower", "Flower", "shake & trim", ["shake & trim"]),
    ("Flower", "Flower", "mixed buds", ["Mixed Buds"]),
    ("Flower", "Flower", "pre-ground", ["pre-ground"]),
    ("Flower", "Flower", "bulk flower", ["bulk flower"]),
    ("Flower", "Flower", "ounce deals", ["$55 smalls ounce", "14 grams cheap",
                                         "14 grams smalls",
                                         "14g smalls 2 pack (2 7g packs)",
                                         "2-pack smalls 1 ounce",
                                         "3.5g dep flower pack",
                                         "Build your own BIGs premium ounce",
                                         "QP smalls variety pack"]),

    # ---- Vaporizers --------------------------------------------------------
    ("Vaporizers", "Vaporizers", "cartridges", ["cartridges",
                                                "1.5g vape cartridge",
                                                "1g THCA cartridge",
                                                "Vape Cartridge",
                                                "Vape cartridge",
                                                "vape cartridge"]),
    ("Vaporizers", "Vaporizers", "disposables", ["disposables",
                                                 "2g Dual flavor disposable",
                                                 "Vape Disposable",
                                                 "mystery 1g disposable",
                                                 "pumkin pie cart and battery"]),
    ("Vaporizers", "Vaporizers", "all-in-one", ["all-in-one", "All-in-One"]),
    ("Vaporizers", "Vaporizers", "pods", ["pods", "Reload Pod"]),
    ("Vaporizers", "Vaporizers", "kits", ["Kit", "Kits"]),
    ("Vaporizers", "Vaporizers", "BRIQ", ["BRIQ"]),
    ("Vaporizers", "Vaporizers", "live resin cartridge",
     ["live resin cartridge"]),
    ("Vaporizers", "Vaporizers", "live resin disposable",
     ["live resin disposable"]),
    ("Vaporizers", "Vaporizers", "STIQ", ["STIQ"]),
    ("Vaporizers", "Vaporizers", "live rosin", ["live-rosin"]),
    ("Vaporizers", "Vaporizers", "live rosin disposable",
     ["live-rosin-disposable"]),
    ("Vaporizers", "Vaporizers", "cured resin cartridge",
     ["cured-resin-cartridge"]),
    ("Vaporizers", "Vaporizers", "cured resin disposable",
     ["cured-resin-disposable"]),
    ("Vaporizers", "Vaporizers", "live resin", ["live-resin"]),

    # ---- Pre-Rolls ---------------------------------------------------------
    ("Pre-Rolls", "Pre-Rolls", "singles", ["singles", "Pre-Roll"]),
    ("Pre-Rolls", "Pre-Rolls", "infused", ["infused",
                                           "single-infused-pre-roll"]),
    ("Pre-Rolls", "Pre-Rolls", "packs", ["packs", "Pre-Roll Pack"]),

    # ---- Tinctures / Topicals / Oral ---------------------------------------
    ("Tinctures", "Tincture", "sprays", ["sprays"]),
    ("Tinctures", "Tincture", "unflavored", ["unflavored"]),
    ("Tinctures", "Tincture", "ratio", ["ratio"]),
    ("Topicals", "Topicals", "balms", ["balms", "Salve"]),
    ("Topicals", "Topicals", "lotions", ["lotions"]),
    ("Topicals", "Topicals", "suppositories", ["suppositories"]),
    ("Topicals", "Topicals", "transdermal patches", ["transdermal patches",
                                                     "Patch"]),
    ("Topicals", "Topicals", "body oil", ["Body Oil"]),
    ("Topicals", "Topicals", "sprays", ["Spray", "Sprays"]),
    ("Oral", "Oral", "tincture", ["Tincture"]),
    ("Oral", "Oral", "capsules", ["Capsules"]),

    # ---- Glass -------------------------------------------------------------
    ("Glass", "Glass", "bongs", ["bongs"]),
    ("Glass", "Glass", "bubblers", ["bubblers"]),
    ("Glass", "Glass", "rigs", ["rigs"]),
    ("Glass", "Glass", "joint bubblers", ["joint bubblers"]),
    ("Glass", "Glass", "beakers", ["45mm beakers", "45mm mini collins beakers",
                                   "5mm beakers", "7mm beakers",
                                   "7mm mini beaker",
                                   "7mm scoped mini beaker", "9mm beakers",
                                   "Beaker", "beakers", "collins beakers",
                                   "frosted beakers", "frosted signature straights",
                                   "full color premium signature beakers",
                                   "full color scoped beakers",
                                   "heavy hit beakers"]),
    ("Glass", "Glass", "straights", ["5mm straights"]),
    ("Glass", "Glass", "signature series", ["full color signature",
                                            "premium series",
                                            "scoped series", "full size"]),
    ("Glass", "Glass", "ash catchers", ["encalmo disc ash catchers"]),
    ("Glass", "Glass", "heady glass", ["Heady Glass", "Hologram Toro",
                                       "Color Models", "Clear Models",
                                       "Clear Models (2nd)", "Clear Slides"]),
    ("Glass", "Glass", "downstems", ["downstems", "danklin coil"]),
    ("Glass", "Glass", "illadelph glass", ["illadelph coils",
                                           "illadelph straight tubes",
                                           "illadelph tubes"]),
    ("Glass", "Glass", "hammers", ["Hammers"]),
    ("Glass", "Glass", "bongs & rigs", ["Bongs & Dab Rigs",
                                        "Waterpipes & Rigs", "Steam Roller",
                                        "Steamroller", "Toro",
                                        "Gravity Infuser", "Gravity Pipe",
                                        "Percolator", "Blunt Bubbler",
                                        "bubbler danklins", "Glass Attachment",
                                        "Glass Bong", "Glass Bubbler",
                                        "Glass Rig", "Glass Water Pipe",
                                        "glass accessories", "glass top",
                                        "Electric Bong",
                                        "Prism Halo Fam Favorites"]),
    ("Glass", "Glass", "wholesale models", ["Wholesale Models"]),

    # ---- Puffco ------------------------------------------------------------
    ("Puffco", "Puffco", "peak pro", ["peak pro"]),
    ("Puffco", "Puffco", "peak", ["peak"]),
    ("Puffco", "Puffco", "pivot", ["pivot"]),
    ("Puffco", "Puffco", "proxy core", ["Proxy Core"]),
    ("Puffco", "Puffco", "peak attachments", ["Peak Attachment",
                                              "Puffco Attachments",
                                              "Puffco Proxy Attachments"]),
    ("Puffco", "Puffco", "puffco accessories", ["Puffco Accessories",
                                                "Official Puffco"]),
    ("Puffco", "Puffco", "charms & joysticks", ["Puffco Charms",
                                                "Puffco Joysticks"]),
    ("Puffco", "Puffco", "mouthpieces", ["Puffco Pivot Mouthpieces",
                                         "Puffco Dry Tops"]),
    ("Puffco", "Puffco", "modül", ["Modül", "Modül Accessories"]),

    # ---- Kits / Skate / Knitwear / Dab Mats / Merch ------------------------
    ("Kits", "Kits", "rig kits", ["Smart Rig Kit"]),
    ("Kits", "Kits", "smoking kits", ["Smoking Kit"]),
    ("Skate", "Skate", "decks", ["Deck", "Skateboard Deck"]),
    ("Skate", "Skate", "skater", ["Skater", "skater"]),
    ("Knitwear", "Knitwear", "knits", ["Knits"]),
    ("Dab Mats", "Dab Mats", "mats", ["Hex Mat", "Dabbing Mat"]),
    ("Merch", "Merch", "stickers", ["Box Stickers", "Die Cut Stickers",
                                    "Sticker Pack"]),
    ("Merch", "Merch", "pins & patches", ["Pin", "Pinback Buttons",
                                          "Patches"]),
    ("Merch", "Merch", "posters", ["Posters"]),

    # ---- Misc --------------------------------------------------------------
    ("Misc", "Misc", "Sale", ["Archives Sale", "Extras Sale", "Clearance",
                              "clearance", "Blowout", "blowout", "Springsale",
                              "springsale"]),
    ("Misc", "Misc", "Deals", ["Deals", "Daily Deals", "Deals - Gear"]),
    ("Misc", "Misc", "Bundle", ["Bundle", "bundle", "Bundle Set", "2pc set"]),
    ("Misc", "Misc", "Drops", ["Current Drops", "current drops",
                               "Current Custom Drop", "current custom drop"]),
    ("Misc", "Misc", "Direct Sale", ["Direct Sale"]),
    ("Misc", "Misc", "Expivi Product Replica", ["Expivi Product Replica"]),
    ("Misc", "Misc", "Other", ["Other", "Other Shit", "H", "Product",
                               "product", "Sign", "sign", "Warranty",
                               "warranty", "Assurance",
                               "Shipping Protection", "Membership",
                               "membership", "Gift With Purchase",
                               "Highlight section", "New Products",
                               "Pallets", "pallets", "Extensions",
                               "extensions", "Inflatable", "Incense",
                               "Ice Pack for shipping", "Lights",
                               "Elite", "Umbrella", "Outdoor"]),
    ("Misc", "Misc", "Home & Decor", ["Bedding", "Blankets", "Canvas",
                                      "Coasters", "Cup", "cup", "Decor",
                                      "Drinkware", "Home Stuff",
                                      "Home accessory", "home accessory",
                                      "Homeware", "Kitchen & Bar", "Mirrors",
                                      "Mug", "mug", "Rug", "rug",
                                      "Tableware", "tableware", "Towel",
                                      "towel", "Vase", "Wallpaper"]),
    ("Misc", "Misc", "Beauty", ["Eyeliner", "Eyes", "Eyeshadow",
                                "Face & Body", "Hair", "Lip Liner",
                                "lip product", "Lips", "Lipstick"]),
    ("Misc", "Misc", "Fun & Games", ["Fun & Games", "Toy", "toy",
                                     "Tarot Cards", "tarot cards"]),
    ("Misc", "Misc", "Car Styling", ["Car Styling"]),
    ("Misc", "Misc", "Pomade", ["Pomade", "pomade"]),
    ("Misc", "Misc", "Collabs", ["Collabs", "collabs", "Juicy J Collab",
                                 "juicy j collab"]),
    ("Misc", "Misc", "Mothership Meltdown", ["Mothership Meltdown"]),
]


def build():
    js_main = {}
    py_main = {}
    js_sub = {}
    py_sub = {}
    collisions = []

    def put(store, k, v, label):
        if k in store and store[k] != v:
            collisions.append(f"{label}: {k!r} -> {store[k]!r} and {v!r}")
        store[k] = v

    for js_name, py_name, raws in MAINS:
        for raw in raws:
            put(js_main, key(raw), js_name, "js main")
            put(py_main, key(raw), py_name, "py main")

    for js_main_name, py_main_name, label, raws in SUBS:
        for raw in raws:
            put(js_sub, key(raw), label, "js sub")
            put(py_sub, (key(py_main_name), key(raw)), label, "py sub")

    return js_main, py_main, js_sub, py_sub, collisions


def emit_js(name, mapping, indent=6):
    """Render a JS object literal with normalised keys, sorted for a stable diff."""
    pad = " " * indent
    lines = [f"const {name} = {{"]
    for k in sorted(mapping):
        lines.append(f"{pad}'{k}': '{mapping[k]}',")
    lines.append("};")
    return "\n".join(lines)


if __name__ == "__main__":
    js_main, py_main, js_sub, py_sub, collisions = build()
    print("collisions:", collisions or "none")
    print("js_main entries:", len(js_main), " py_main entries:", len(py_main))
    print("js_sub entries:", len(js_sub), " py_sub entries:", len(py_sub))
    if collisions:
        raise SystemExit(
            "two raw names normalise to the same key with different canonical "
            "labels; resolve them in the table above"
        )
    print("table is consistent; run apply_py_aliases.py then apply_js_maps.py")
