"""Canonical dispensary category names.

Every store names its shelves differently. Dutchie reports ``Concentrate``,
Klutch scrapes ``/collections/concentrates`` and calls it ``Concentrates``, and
a stale snapshot carried ``Vapes`` where the live data says ``Vaporizers``.
Left alone, the same shelf shows up as two rows in the sidebar and splits the
"Deals only" category breakdown.

The canonical forms below are the ones the live Dutchie data uses, so nothing
that is already consistent gets renamed.
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional

from config import Config

# Anything not listed is left untouched rather than guessed at.
CATEGORY_ALIASES = {
    # Concentrate and every synonym Dutchie or Klutch uses for the same shelf.
    "concentrate": "Concentrate",
    "concentrates": "Concentrate",
    "extract": "Concentrate",
    "extracts": "Concentrate",
    "hash": "Concentrate",
    "concentraterigs": "Concentrate",
    "concentraterig": "Concentrate",
    "dabrig": "Concentrate",
    "dabrigs": "Concentrate",
    "oilrig": "Concentrate",
    "oilrigs": "Concentrate",
    "carbcap": "Concentrate",
    "carbcaps": "Concentrate",
    "carb": "Concentrate",
    "concentrateaccessories": "Concentrate",
    "concentrateaccessory": "Concentrate",
    "dabaccessories": "Concentrate",
    "dabaccessory": "Concentrate",
    "quartz": "Concentrate",
    "banger": "Concentrate",
    "bangers": "Concentrate",
    "nail": "Concentrate",
    "nails": "Concentrate",
    "terpslurper": "Concentrate",
    "terpslurpers": "Concentrate",
    "terppearl": "Concentrate",
    "terppearls": "Concentrate",
    "pearl": "Concentrate",
    "pearls": "Concentrate",
    # Vaporizers.
    "vaporizers": "Vaporizers",
    "vaporizer": "Vaporizers",
    "vapes": "Vaporizers",
    "vape": "Vaporizers",
    "carts": "Vaporizers",
    "cartridges": "Vaporizers",
    "erigs": "Vaporizers",
    "erig": "Vaporizers",
    "erigsvaporizers": "Vaporizers",
    "electronicrig": "Vaporizers",
    "electronicrigs": "Vaporizers",
    # Edibles.
    "edible": "Edible",
    "edibles": "Edible",
    # Pre-rolls, which are only ever spelled inconsistently.
    "preroll": "Pre-Rolls",
    "prerolls": "Pre-Rolls",
    # Flower.
    "flower": "Flower",
    "flowers": "Flower",
    # Tinctures.
    "tincture": "Tincture",
    "tinctures": "Tincture",
    # Topicals, which the live data keeps plural.
    "topical": "Topicals",
    "topicals": "Topicals",
    # Accessories - consolidate all accessory types.
    "accessory": "Accessories",
    "accessories": "Accessories",
    "rollingcones": "Accessories",
    "rollingconesaccessories": "Accessories",
    "cleaningsupplies": "Accessories",
    "cleaningsupply": "Accessories",
    "cleaning": "Accessories",
    "batteries": "Accessories",
    "battery": "Accessories",
    # Glass - consolidate glass pieces.
    "bong": "Glass",
    "bongs": "Glass",
    "rig": "Glass",
    "rigs": "Glass",
    "bubbler": "Glass",
    "bubblers": "Glass",
    "ashcatcher": "Glass",
    "ashcatchers": "Glass",
    "bowl": "Glass",
    "bowls": "Glass",
    "pipe": "Glass",
    "pipes": "Glass",
    "mouthpiece": "Glass",
    "mouthpieces": "Glass",
    "jointbubbler": "Glass",
    "jointbubblers": "Glass",
    "waterpipe": "Glass",
    "waterpipes": "Glass",
    "waterpipe": "Glass",
    "waterpipes": "Glass",
    "slide": "Glass",
    "slides": "Glass",
    "flowerpipe": "Glass",
    "flowerpipes": "Glass",
    "flowerpipesandaccessories": "Glass",
    "pendant": "Glass",
    "pendants": "Glass",
    # Puffco devices and accessories.
    "peak": "Puffco",
    "peakaccessories": "Puffco",
    "peakpro": "Puffco",
    "peakproaccessories": "Puffco",
    "pivot": "Puffco",
    "pivotaccessories": "Puffco",
    "pivotaccessory": "Puffco",
    "proxyaccessory": "Puffco",
    "proxycoreaccessory": "Puffco",
    # Misc accessory types that go under Accessories.
    "batteries": "Accessories",
    "battery": "Accessories",
    "charger": "Accessories",
    "chargers": "Accessories",
    "grinder": "Accessories",
    "grinders": "Accessories",
    "lighter": "Accessories",
    "lighters": "Accessories",
    "lightercases": "Accessories",
    "lightercase": "Accessories",
    "tray": "Accessories",
    "trays": "Accessories",
    "rollingtray": "Accessories",
    "rollingtrays": "Accessories",
    "storage": "Accessories",
    "jointcase": "Accessories",
    "jointcases": "Accessories",
    "jointholder": "Accessories",
    "jointholders": "Accessories",
    "rollingpapers": "Accessories",
    "rollingpaper": "Accessories",
    "cone": "Accessories",
    "cones": "Accessories",
    "ashtray": "Accessories",
    "ashtrays": "Accessories",
    "dabaccessories": "Accessories",
    "dabaccessory": "Accessories",
    "dabtools": "Accessories",
    "dabtool": "Accessories",
    "tools": "Accessories",
    "tool": "Accessories",
    "replacementpart": "Accessories",
    "replacementparts": "Accessories",
    "protection": "Accessories",
    "pearl": "Accessories",
    "pearls": "Accessories",
    "glassware": "Accessories",
    "character": "Accessories",
    # Gift cards.
    "giftcard": "Gift Cards",
    "giftcards": "Gift Cards",
    # Kits.
    "kit": "Kits",
    "kits": "Kits",
    # Dab mats get their own shelf. A mat is a large silicone sheet rather than
    # a dab tool, so folding it into "dab tools" would hide the biggest items
    # on the shelf behind the smallest, and "mat" on its own is used by stores
    # that mean nothing else.
    "dabmat": "Dab Mats",
    "dabmats": "Dab Mats",
    "dab-mat": "Dab Mats",
    "dab-mats": "Dab Mats",
    "dabpad": "Dab Mats",
    "dabpads": "Dab Mats",
    "mat": "Dab Mats",
    "mats": "Dab Mats",
    # "cleaningcare" folds cleaning supplies into Accessories, which already
    # owns the plain "cleaning" alias above. Vape coils are replacement parts.
    "cleaningcare": "Accessories",
    "cleaningsupplies": "Accessories",
    "cleaningsupply": "Accessories",
    "coil": "Accessories",
    "coils": "Accessories",
    # Event and artist drops from the glass stores are still glass art.
    "ohioglassblowersshow2025": "Glass",
    "ohioglassblowersshow": "Glass",
    "stevesizelovedrop2025": "Glass",
    "stevesizelovedrop": "Glass",
    # Donation and Insurance are not product shelves; fold them into Misc.
    "donation": "Misc",
    "insurance": "Misc",
    "misc": "Misc",
    # Merch.
    "merch": "Merch",
    "merchandise": "Merch",

    # Apparel. Clothing stores name the same garment differently, and a
    # wholesale taxonomy uses ALL-CAPS codes for the same shelves.
    "active": "Apparel",
    "anklesocks": "Apparel",
    "apparel": "Apparel",
    "bellbottoms": "Apparel",
    "belt": "Apparel",
    "belts": "Apparel",
    "beltsharnesses": "Apparel",
    "bikini": "Apparel",
    "blazer": "Apparel",
    "blouse": "Apparel",
    "bodycon": "Apparel",
    "bodysuit": "Apparel",
    "bolero": "Apparel",
    "bottomknitpant": "Apparel",
    "bottomknitshort": "Apparel",
    "bottomprintedpant": "Apparel",
    "bottomprintedshort": "Apparel",
    "bottoms": "Apparel",
    "bottomswimtrunk": "Apparel",
    "bottomwindbreakerpant": "Apparel",
    "bottomwovenpant": "Apparel",
    "boxers": "Apparel",
    "bralet": "Apparel",
    "cardigan": "Apparel",
    "cardigans": "Apparel",
    "cloak": "Apparel",
    "clothing": "Apparel",
    "clothingdropship": "Apparel",
    "coat": "Apparel",
    "coats": "Apparel",
    "corset": "Apparel",
    "corsets": "Apparel",
    "costumes": "Apparel",
    "crewneckfleeceprinted": "Apparel",
    "crewneckprintedfleece": "Apparel",
    "croptop": "Apparel",
    "denim": "Apparel",
    "dresses": "Apparel",
    "duster": "Apparel",
    "flares": "Apparel",
    "gloves": "Apparel",
    "handmadebelts": "Apparel",
    "harness": "Apparel",
    "harnesses": "Apparel",
    "hatsscarvesgloves": "Apparel",
    "hoodedfleececutsew": "Apparel",
    "hoodie": "Apparel",
    "hoodies": "Apparel",
    "hoodiessweats": "Apparel",
    "hoodyfleeceprinted": "Apparel",
    "jacket": "Apparel",
    "jackets": "Apparel",
    "jersey": "Apparel",
    "joggershorts": "Apparel",
    "jumpsuit": "Apparel",
    "jumpsuits": "Apparel",
    "jumpsuitsplaysuits": "Apparel",
    "jumpsuitsrompers": "Apparel",
    "kids": "Apparel",
    "knitdress": "Apparel",
    "knitlstop": "Apparel",
    "knitsstop": "Apparel",
    "knittankcutsew": "Apparel",
    "kuties": "Apparel",
    "leggings": "Apparel",
    "legwarmers": "Apparel",
    "lingerie": "Apparel",
    "lingeriesleepwear": "Apparel",
    "longsleeve": "Apparel",
    "longsocks": "Apparel",
    "maxi": "Apparel",
    "mensblackstyletshirt": "Apparel",
    "mensindigostyletshirt": "Apparel",
    "mensmilitarygreenstyletshirt": "Apparel",
    "midi": "Apparel",
    "mini": "Apparel",
    "outerwear": "Apparel",
    "outerwearjacketcutsew": "Apparel",
    "outerwearwindbreakercutsew": "Apparel",
    "pants": "Apparel",
    "panty": "Apparel",
    "pastiestatts": "Apparel",
    "playsuit": "Apparel",
    "rompers": "Apparel",
    "sarong": "Apparel",
    "scarf": "Apparel",
    "scarfslides": "Apparel",
    "scarves": "Apparel",
    "scarvesgloves": "Apparel",
    "shirt": "Apparel",
    "shirts": "Apparel",
    "shirtsblouses": "Apparel",
    "shorts": "Apparel",
    "shortsleeve": "Apparel",
    "skirt": "Apparel",
    "skirts": "Apparel",
    "socks": "Apparel",
    "sockstights": "Apparel",
    "standardtee": "Apparel",
    "stockings": "Apparel",
    "sweater": "Apparel",
    "sweaterdress": "Apparel",
    "sweaters": "Apparel",
    "sweatpants": "Apparel",
    "sweats": "Apparel",
    "sweatshirt": "Apparel",
    "swim": "Apparel",
    "swimsuit": "Apparel",
    "tank": "Apparel",
    "tee": "Apparel",
    "teelsprinted": "Apparel",
    "tees": "Apparel",
    "teessprinted": "Apparel",
    "tights": "Apparel",
    "tops": "Apparel",
    "trousers": "Apparel",
    "trousersshorts": "Apparel",
    "trunks": "Apparel",
    "tshirt": "Apparel",
    "tshirts": "Apparel",
    "tunic": "Apparel",
    "veil": "Apparel",
    "vest": "Apparel",
    "vtgtops": "Apparel",
    "wideleg": "Apparel",
    "womensblackstyletshirt": "Apparel",
    "womensheathergreystyletshirt": "Apparel",
    "wovenlstop": "Apparel",
    "wovensstop": "Apparel",

    # Hats, including the headwear codes and the cap/beanie spellings.
    "accdadhat": "Hats",
    "accsnapback": "Hats",
    "accsnapbackhat": "Hats",
    "acctruckerhat": "Hats",
    "capbundle": "Hats",
    "caps": "Hats",
    "fedora": "Hats",
    "handmadehats": "Hats",
    "hat": "Hats",
    "hats": "Hats",
    "headwear": "Hats",

    # Beanies, which are a separate shelf from hats in the source data.
    "accknitbeanie": "Beanies",
    "beanie": "Beanies",
    "beanies": "Beanies",
    "toque": "Beanies",

    # Bags. Every store spells a bag differently, and the wallets section
    # is the same shelf.
    "accshoulderbag": "Bags",
    "accwovenbackpack": "Bags",
    "backpack": "Bags",
    "bags": "Bags",
    "bagswallets": "Bags",
    "coinpurse": "Bags",
    "crossbody": "Bags",
    "duffle": "Bags",
    "handbag": "Bags",
    "handbags": "Bags",
    "luggage": "Bags",
    "messenger": "Bags",
    "tote": "Bags",
    "totebag": "Bags",
    "wallet": "Bags",
    "weekendbag": "Bags",

    # Footwear. Boots, platforms and slides are all the same shelf.
    "accfootwear": "Footwear",
    "boots": "Footwear",
    "bootsbooties": "Footwear",
    "creepers": "Footwear",
    "flats": "Footwear",
    "flipflop": "Footwear",
    "footwear": "Footwear",
    "heels": "Footwear",
    "platformboots": "Footwear",
    "platforms": "Footwear",
    "sandal": "Footwear",
    "sandals": "Footwear",
    "shoes": "Footwear",
    "sneakers": "Footwear",
    "wedges": "Footwear",

    # Accessories. One-off shelves from the glass and smoke shops.
    "accesory": "Accessories",
    "accmiscellaneous": "Accessories",
    "adapters": "Accessories",
    "atomizer": "Accessories",
    "beads": "Accessories",
    "blunttips": "Accessories",
    "bobmarley": "Accessories",
    "bowlpiece": "Accessories",
    "bracelet": "Accessories",
    "cannabuttermaker": "Accessories",
    "case": "Accessories",
    "chillstraw": "Accessories",
    "chillum": "Accessories",
    "choker": "Accessories",
    "cleaningproducts": "Accessories",
    "clearsolidpipes": "Accessories",
    "container": "Accessories",
    "dabbingaccessories": "Accessories",
    "dealsdrypipes": "Accessories",
    "dryherbpipe": "Accessories",
    "drypipe": "Accessories",
    "dugout": "Accessories",
    "earrings": "Accessories",
    "electricpipe": "Accessories",
    "electronicdabtool": "Accessories",
    "encalmodiscashcatchers": "Accessories",
    "gasmask": "Accessories",
    "glasspipe": "Accessories",
    "glycerinestraw": "Accessories",
    "hairaccessories": "Accessories",
    "hairaccessory": "Accessories",
    "handpipe": "Accessories",
    "handpipes": "Accessories",
    "jars": "Accessories",
    "jewelry": "Accessories",
    "keychain": "Accessories",
    "lanyard": "Accessories",
    "lighter3pack": "Accessories",
    "lighterholder": "Accessories",
    "marbles": "Accessories",
    "mysterymarble": "Accessories",
    "necklace": "Accessories",
    "necklaces": "Accessories",
    "necklaceschokers": "Accessories",
    "opalspheres": "Accessories",
    "saberaccessory": "Accessories",
    "scrunchie": "Accessories",
    "sherlockpipe": "Accessories",
    "siliconeaccessorykit": "Accessories",
    "smokemiscellaneous": "Accessories",
    "smokingaccessories": "Accessories",
    "smokingpipe": "Accessories",
    "solidpipes": "Accessories",
    "spoonpipe": "Accessories",
    "sunglasses": "Accessories",
    "terpjars": "Accessories",
    "terppillar": "Accessories",
    "terptimer": "Accessories",
    "tether": "Accessories",
    "thedopestbattery": "Accessories",
    "vapeaccessory": "Accessories",
    "vaporizeraccessories": "Accessories",
    "wholesaleaccessories": "Accessories",
    "zippo": "Accessories",

    # Concentrate. Diamonds, quartz and hash are all concentrates.
    "2gliquiddiamonds": "Concentrate",
    "bangerbasket": "Concentrate",
    "iceguyshash": "Concentrate",
    "liquiddiamonds": "Concentrate",
    "nectarcollector": "Concentrate",
    "quartzbanger": "Concentrate",
    "slurpercaps": "Concentrate",
    "statichash": "Concentrate",
    "thcadiamonds": "Concentrate",

    # Edible. Beverages and syrups are drunk, not smoked.
    "beverage": "Edible",
    "gummysharks": "Edible",
    "syrup": "Edible",
    "syrupbuilder3for60": "Edible",
    "thedopestcubesgummies": "Edible",

    # Flower. Ounce and smalls deals are still flower.
    "14gramscheap": "Flower",
    "14gramssmalls": "Flower",
    "14gsmalls2pack27gpacks": "Flower",
    "2packsmalls1ounce": "Flower",
    "35gdepflowerpack": "Flower",
    "55smallsounce": "Flower",
    "7gramspremiumflower": "Flower",
    "buildyourownbigspremiumounce": "Flower",
    "flowervarietypackpremium": "Flower",
    "indoorflower": "Flower",
    "premiumdepflower": "Flower",
    "premiumdepflower95ounce": "Flower",
    "qpsmallsvarietypack": "Flower",

    # Vaporizers. A 1g cartridge and a 2g disposable are both vapes.
    "15gvapecartridge": "Vaporizers",
    "1gthcacartridge": "Vaporizers",
    "2gdualflavordisposable": "Vaporizers",
    "mystery1gdisposable": "Vaporizers",
    "pumkinpiecartandbattery": "Vaporizers",
    "vapecartridge": "Vaporizers",
    "vapedisposable": "Vaporizers",

    # Oral products, which Dutchie reports as their own shelf.
    "oral": "Oral",

    # Glass. Beaker sizes, Prism series and artist drops are all glass art.
    "45mmbeakers": "Glass",
    "45mmminicollinsbeakers": "Glass",
    "5mmbeakers": "Glass",
    "5mmstraights": "Glass",
    "7mmbeakers": "Glass",
    "7mmminibeaker": "Glass",
    "7mmscopedminibeaker": "Glass",
    "9mmbeakers": "Glass",
    "beaker": "Glass",
    "beakers": "Glass",
    "bluntbubbler": "Glass",
    "bongsdabrigs": "Glass",
    "bubblerdanklins": "Glass",
    "clearmodels": "Glass",
    "clearmodels2nd": "Glass",
    "clearslides": "Glass",
    "collinsbeakers": "Glass",
    "colormodels": "Glass",
    "danklincoil": "Glass",
    "downstems": "Glass",
    "electricbong": "Glass",
    "frostedbeakers": "Glass",
    "frostedsignaturestraights": "Glass",
    "fullcolorpremiumsignaturebeakers": "Glass",
    "fullcolorscopedbeakers": "Glass",
    "fullcolorsignature": "Glass",
    "fullsize": "Glass",
    "glass": "Glass",
    "glassaccessories": "Glass",
    "glassattachment": "Glass",
    "glassbong": "Glass",
    "glassbubbler": "Glass",
    "glassrig": "Glass",
    "glasstop": "Glass",
    "glasswaterpipe": "Glass",
    "gravityinfuser": "Glass",
    "gravitypipe": "Glass",
    "hammers": "Glass",
    "headyglass": "Glass",
    "heavyhitbeakers": "Glass",
    "hologramtoro": "Glass",
    "illadelphcoils": "Glass",
    "illadelphstraighttubes": "Glass",
    "illadelphtubes": "Glass",
    "percolator": "Glass",
    "premiumseries": "Glass",
    "prismhalofamfavorites": "Glass",
    "scopedseries": "Glass",
    "steamroller": "Glass",
    "toro": "Glass",
    "waterpipesrigs": "Glass",
    "wholesalemodels": "Glass",

    # Puffco. Modul, charms and attachments are Puffco accessories.
    "modlaccessories": "Puffco",
    "modul": "Modül",
    "officialpuffco": "Puffco",
    "peakattachment": "Puffco",
    "proxycore": "Puffco",
    "puffco": "Puffco",
    "puffcoaccessories": "Puffco",
    "puffcoattachments": "Puffco",
    "puffcocharms": "Puffco",
    "puffcodrytops": "Puffco",
    "puffcojoysticks": "Puffco",
    "puffcopivotmouthpieces": "Puffco",
    "puffcoproxyattachments": "Puffco",

    # Kits.
    "smartrigkit": "Kits",
    "smokingkit": "Kits",

    # Merch.
    "boxstickers": "Merch",
    "diecutstickers": "Merch",
    "patches": "Merch",
    "pin": "Merch",
    "pinbackbuttons": "Merch",
    "posters": "Merch",
    "stickerpack": "Merch",

    # Skate.
    "deck": "Skate",
    "skate": "Skate",
    "skateboarddeck": "Skate",
    "skater": "Skate",

    # Dab Mats.
    "dabbingmat": "Dab Mats",
    "hexmat": "Dab Mats",
    "mousepad": "Dab Mats",
    "mousepads": "Dab Mats",

    # Knitwear.
    "knits": "Knitwear",
    "knitwear": "Knitwear",

    # Misc. Sale flags, service line items, placeholders and home goods
    # are not product shelves, so they collapse onto the catch-all.
    "2pcset": "Misc",
    "archivessale": "Misc",
    "assurance": "Misc",
    "bedding": "Misc",
    "blanket": "Misc",
    "blankets": "Misc",
    "blowout": "Misc",
    "bundle": "Misc",
    "bundleset": "Misc",
    "canvas": "Misc",
    "carstyling": "Misc",
    "clearance": "Misc",
    "coasters": "Misc",
    "collabs": "Misc",
    "cup": "Misc",
    "currentcustomdrop": "Misc",
    "currentdrops": "Misc",
    "dailydeals": "Misc",
    "deals": "Misc",
    "dealsgear": "Misc",
    "decor": "Misc",
    "directsale": "Misc",
    "drinkware": "Misc",
    "elite": "Misc",
    "essentials99subscriptionpack": "Misc",
    "expiviproductreplica": "Misc",
    "extensions": "Misc",
    "extrassale": "Misc",
    "eyeliner": "Misc",
    "eyes": "Misc",
    "eyeshadow": "Misc",
    "facebody": "Misc",
    "fungames": "Misc",
    "giftwithpurchase": "Misc",
    "h": "Misc",
    "hair": "Misc",
    "heavyweight175subscriptionpack": "Misc",
    "highlightsection": "Misc",
    "homeaccessory": "Misc",
    "homestuff": "Misc",
    "homeware": "Misc",
    "icepackforshipping": "Misc",
    "incense": "Misc",
    "inflatable": "Misc",
    "juicyjcollab": "Misc",
    "kitchenbar": "Misc",
    "lights": "Misc",
    "lipliner": "Misc",
    "lipproduct": "Misc",
    "lips": "Misc",
    "lipstick": "Misc",
    "membership": "Misc",
    "mirrors": "Misc",
    "mothershipmeltdown": "Misc",
    "mug": "Misc",
    "newproducts": "Misc",
    "other": "Misc",
    "othershit": "Misc",
    "outdoor": "Misc",
    "pallets": "Misc",
    "pomade": "Misc",
    "product": "Misc",
    "rug": "Misc",
    "shippingprotection": "Misc",
    "sign": "Misc",
    "springsale": "Misc",
    "subscriptionbox": "Misc",
    "tableware": "Misc",
    "tarotcards": "Misc",
    "towel": "Misc",
    "toy": "Misc",
    "umbrella": "Misc",
    "uncategorized": "Misc",
    "vase": "Misc",
    "wallpaper": "Misc",
    "warranty": "Misc",
}

SUB_SEPARATOR = " \u00b7 "

_KEY_RE = re.compile(r"[^a-z0-9]+")


def category_key(name: str) -> str:
    """Comparison key for a category name, ignoring spacing and punctuation."""
    return _KEY_RE.sub("", (name or "").lower())


def main_category(category: str) -> str:
    """The top-level category, with any subcategory removed."""
    return (category or "").split(SUB_SEPARATOR.strip(), 1)[0].strip()


def sub_category(category: str) -> str:
    """The subcategory part after the separator, or an empty string."""
    parts = (category or "").split(SUB_SEPARATOR.strip(), 1)
    return parts[1].strip() if len(parts) > 1 else ""


# Subcategory names that mean the same shelf but are written differently by
# different stores. Keyed by (main category key, subcategory key) so a rename
# can never leak across shelves - "infused" under Pre-Rolls has nothing to do
# with "infused-flower" under Concentrate.
#
# Within Pre-Rolls, every way of saying an infused pack collapses to "infused".
# One store calls the shelf "infused", another "infused-pre-roll-pack", and a
# third writes "Infused Pre Roll 5-Pack", all for the same thing. Left alone
# they appear as three separate rows in the sidebar and split the counts.
SUBCATEGORY_ALIASES = {
    # Pre-Rolls subcategories
    ("prerolls", "infused"): "infused",
    ("prerolls", "infusedprerollpack"): "infused",
    ("prerolls", "infusedprerollpacks"): "infused",
    ("prerolls", "infusedpack"): "infused",
    ("prerolls", "infusedpacks"): "infused",
    ("prerolls", "infusedpreroll"): "infused",
    ("prerolls", "infusedprerolls"): "infused",
    ("prerolls", "singles"): "singles",
    ("prerolls", "single"): "singles",
    ("prerolls", "packs"): "packs",
    ("prerolls", "pack"): "packs",

    # Concentrate subcategories
    ("concentrate", "liveresin"): "live resin",
    ("concentrate", "liveresindisposable"): "live resin disposable",
    ("concentrate", "liveresincartridge"): "live resin cartridge",
    ("concentrate", "rosin"): "rosin",
    ("concentrate", "liverosin"): "live rosin",
    ("concentrate", "badder"): "badder",
    ("concentrate", "budder"): "budder",
    ("concentrate", "shatter"): "shatter",
    ("concentrate", "sauce"): "sauce",
    ("concentrate", "sugar"): "sugar",
    ("concentrate", "crumble"): "crumble",
    ("concentrate", "wax"): "wax",
    ("concentrate", "rso"): "rso",
    ("concentrate", "applicators"): "applicators",
    ("concentrate", "applicator"): "applicators",
    ("concentrate", "infusedflower"): "infused-flower",

    # Edible subcategories
    ("edible", "gummies"): "gummies",
    ("edible", "gummy"): "gummies",
    ("edible", "liveresingummies"): "live resin gummies",
    ("edible", "liverosingummies"): "live rosin gummies",
    ("edible", "chocolates"): "chocolates",
    ("edible", "chocolate"): "chocolates",
    ("edible", "drinks"): "drinks",
    ("edible", "drink"): "drinks",
    ("edible", "beverages"): "drinks",
    ("edible", "hardcandy"): "hard candy",
    ("edible", "capsulestablets"): "capsules & tablets",
    ("edible", "capsules&tablets"): "capsules & tablets",
    ("edible", "tablets"): "capsules & tablets",
    ("edible", "dissolvables"): "dissolvables",
    ("edible", "dissolvable"): "dissolvables",
    ("edible", "mints"): "mints",
    ("edible", "mint"): "mints",

    # Flower subcategories
    ("flower", "smallbuds"): "small buds",
    ("flower", "shaketrim"): "shake & trim",
    ("flower", "shake&trim"): "shake & trim",
    ("flower", "premium"): "premium",
    ("flower", "wholeflower"): "whole flower",
    ("flower", "bulkflower"): "bulk flower",
    ("flower", "preground"): "pre-ground",

    # Vaporizers subcategories
    ("vaporizers", "disposables"): "disposables",
    ("vaporizers", "disposable"): "disposables",
    ("vaporizers", "cartridges"): "cartridges",
    ("vaporizers", "cartridge"): "cartridges",
    ("vaporizers", "pods"): "pods",
    ("vaporizers", "pod"): "pods",
    ("vaporizers", "liveresindisposable"): "live resin disposable",
    ("vaporizers", "liveresincartridge"): "live resin cartridge",

    # Accessories subcategories
    ("accessories", "batteries"): "batteries",
    ("accessories", "battery"): "batteries",
    ("accessories", "devices"): "devices",
    ("accessories", "device"): "devices",
    ("accessories", "grinders"): "grinders",
    ("accessories", "grinder"): "grinders",
    ("accessories", "lighters"): "lighters",
    ("accessories", "lighter"): "lighters",
    ("accessories", "trays"): "trays",
    ("accessories", "tray"): "trays",
    ("accessories", "glassware"): "glassware",
    ("accessories", "dabtools"): "dab tools",
    ("accessories", "dabtool"): "dab tools",
    # Keys are normalised, so "dab-mats" and "dab mats" both arrive as dabmats.
    ("accessories", "dabmats"): "dab mats",
    ("accessories", "dabmat"): "dab mats",
    ("accessories", "mats"): "dab mats",
    ("accessories", "mat"): "dab mats",
    ("accessories", "papersrollingsupplies"): "papers & rolling supplies",
    ("accessories", "papersrollingsupplies"): "papers & rolling supplies",
    ("accessories", "ashtrays"): "ashtrays",
    ("accessories", "ashtray"): "ashtrays",
    ("accessories", "cones"): "cones",
    ("accessories", "cone"): "cones",
    ("accessories", "rollingpapers"): "rolling papers",
    ("accessories", "rollingpaper"): "rolling papers",
    ("accessories", "rollingtrays"): "rolling trays",
    ("accessories", "rollingtray"): "rolling trays",
    ("accessories", "storage"): "storage",
    ("accessories", "jointcases"): "joint cases",
    ("accessories", "jointcase"): "joint cases",
    ("accessories", "jointholders"): "joint holders",
    ("accessories", "jointholder"): "joint holders",
    ("accessories", "lightercases"): "lighter cases",
    ("accessories", "lightercase"): "lighter cases",
    ("accessories", "tools"): "tools",
    ("accessories", "tool"): "tools",
    ("accessories", "replacementparts"): "replacement parts",
    ("accessories", "replacementpart"): "replacement parts",
    ("accessories", "ashcatchers"): "ash catchers",
    ("accessories", "ashcatcher"): "ash catchers",
    ("accessories", "bowls"): "bowls",
    ("accessories", "bowl"): "bowls",
    ("accessories", "pipes"): "pipes",
    ("accessories", "pipe"): "pipes",
    ("accessories", "mouthpieces"): "mouthpieces",
    ("accessories", "mouthpiece"): "mouthpieces",
    ("accessories", "protection"): "protection",
    ("accessories", "pearls"): "pearls",
    ("accessories", "pearl"): "pearls",
    ("accessories", "chargers"): "chargers",
    ("accessories", "charger"): "chargers",

    # Glass subcategories
    ("glass", "bongs"): "bongs",
    ("glass", "bong"): "bongs",
    ("glass", "rigs"): "rigs",
    ("glass", "rig"): "rigs",
    ("glass", "bubblers"): "bubblers",
    ("glass", "bubbler"): "bubblers",
    ("glass", "jointbubblers"): "joint bubblers",
    ("glass", "jointbubbler"): "joint bubblers",

    # Puffco subcategories
    ("puffco", "peak"): "peak",
    ("puffco", "peakaccessories"): "peak accessories",
    ("puffco", "peakpro"): "peak pro",
    ("puffco", "peakproaccessories"): "peak pro accessories",
    ("puffco", "pivot"): "pivot",
    ("puffco", "pivotaccessories"): "pivot accessories",
    ("puffco", "pivotaccessory"): "pivot accessories",
    ("puffco", "proxyaccessories"): "proxy accessories",
    ("puffco", "proxyaccessory"): "proxy accessories",
    ("puffco", "proxycoreaccessories"): "proxy core accessories",
    ("puffco", "proxycoreaccessory"): "proxy core accessories",

    # Tincture subcategories
    ("tincture", "sprays"): "sprays",
    ("tincture", "spray"): "sprays",
    ("tincture", "unflavored"): "unflavored",
    ("tincture", "ratio"): "ratio",

    # Topicals subcategories
    ("topicals", "balms"): "balms",
    ("topicals", "balm"): "balms",
    ("topicals", "lotions"): "lotions",
    ("topicals", "lotion"): "lotions",
    ("topicals", "transdermalpatches"): "transdermal patches",
    ("topicals", "suppositories"): "suppositories",
    ("topicals", "suppository"): "suppositories",

    # Apparel subcategories: the wholesale taxonomy codes and every
    # singular/plural and case variant of the same garment.
    ("apparel", "active"): "Activewear",
    ("apparel", "anklesocks"): "Ankle Socks",
    ("apparel", "apparel"): "Clothing",
    ("apparel", "bellbottoms"): "Flared Pants",
    ("apparel", "belt"): "Belts",
    ("apparel", "belts"): "Belts",
    ("apparel", "beltsharnesses"): "Belts",
    ("apparel", "bikini"): "Swim",
    ("apparel", "blazer"): "Jackets",
    ("apparel", "blouse"): "Blouses",
    ("apparel", "bodycon"): "Corsets",
    ("apparel", "bodysuit"): "Bodysuits",
    ("apparel", "bolero"): "Jackets",
    ("apparel", "bottomknitpant"): "Knit Pants",
    ("apparel", "bottomknitshort"): "Knit Shorts",
    ("apparel", "bottomprintedpant"): "Printed Pants",
    ("apparel", "bottomprintedshort"): "Printed Shorts",
    ("apparel", "bottomswimtrunk"): "Swim Trunks",
    ("apparel", "bottomwindbreakerpant"): "Windbreaker Pants",
    ("apparel", "bottomwovenpant"): "Woven Pants",
    ("apparel", "boxers"): "Boxers",
    ("apparel", "bralet"): "Lingerie",
    ("apparel", "cardigan"): "Cardigans",
    ("apparel", "cardigans"): "Cardigans",
    ("apparel", "cloak"): "Coats",
    ("apparel", "clothing"): "Clothing",
    ("apparel", "clothingdropship"): "Clothing",
    ("apparel", "coat"): "Coats",
    ("apparel", "coats"): "Coats",
    ("apparel", "corset"): "Corsets",
    ("apparel", "corsets"): "Corsets",
    ("apparel", "costumes"): "Costumes",
    ("apparel", "crewneckfleeceprinted"): "Crewneck Fleece",
    ("apparel", "crewneckprintedfleece"): "Crewneck Fleece",
    ("apparel", "croptop"): "Crop Tops",
    ("apparel", "denim"): "Pants",
    ("apparel", "dresses"): "Dresses",
    ("apparel", "duster"): "Coats",
    ("apparel", "flares"): "Flared Pants",
    ("apparel", "gloves"): "Scarves & Gloves",
    ("apparel", "handmadebelts"): "Belts",
    ("apparel", "harness"): "Belts",
    ("apparel", "harnesses"): "Belts",
    ("apparel", "hatsscarvesgloves"): "Scarves & Gloves",
    ("apparel", "hoodedfleececutsew"): "Hooded Fleece",
    ("apparel", "hoodie"): "Hoodies",
    ("apparel", "hoodies"): "Hoodies",
    ("apparel", "hoodiessweats"): "Sweaters",
    ("apparel", "hoodyfleeceprinted"): "Hooded Fleece",
    ("apparel", "jacket"): "Jackets",
    ("apparel", "jackets"): "Jackets",
    ("apparel", "jersey"): "Jersey",
    ("apparel", "joggershorts"): "Shorts",
    ("apparel", "jumpsuit"): "Jumpsuits",
    ("apparel", "jumpsuits"): "Jumpsuits",
    ("apparel", "jumpsuitsplaysuits"): "Jumpsuits",
    ("apparel", "jumpsuitsrompers"): "Jumpsuits",
    ("apparel", "kids"): "Kids",
    ("apparel", "knitdress"): "Knit Dress",
    ("apparel", "knitlstop"): "Long Sleeve Knit Top",
    ("apparel", "knitsstop"): "Short Sleeve Knit Top",
    ("apparel", "knittankcutsew"): "Knit Tank",
    ("apparel", "kuties"): "Kids",
    ("apparel", "leggings"): "Leggings",
    ("apparel", "legwarmers"): "Leg Warmers",
    ("apparel", "lingerie"): "Lingerie",
    ("apparel", "lingeriesleepwear"): "Lingerie",
    ("apparel", "longsleeve"): "Tops",
    ("apparel", "longsleevetee"): "T-Shirts",
    ("apparel", "longsocks"): "Socks",
    ("apparel", "maxi"): "Dresses",
    ("apparel", "mensblackstyletshirt"): "Sets",
    ("apparel", "mensindigostyletshirt"): "Sets",
    ("apparel", "mensmilitarygreenstyletshirt"): "Sets",
    ("apparel", "midi"): "Dresses",
    ("apparel", "mini"): "Dresses",
    ("apparel", "outerwear"): "Outerwear",
    ("apparel", "outerwearjacketcutsew"): "Jacket",
    ("apparel", "outerwearwindbreakercutsew"): "Windbreaker",
    ("apparel", "pants"): "Pants",
    ("apparel", "panty"): "Lingerie",
    ("apparel", "pastiestatts"): "Lingerie",
    ("apparel", "playsuit"): "Jumpsuits",
    ("apparel", "rompers"): "Jumpsuits",
    ("apparel", "sarong"): "Swim",
    ("apparel", "scarf"): "Scarves & Gloves",
    ("apparel", "scarfslide"): "Scarves & Gloves",
    ("apparel", "scarfslides"): "Scarves & Gloves",
    ("apparel", "scarvesgloves"): "Scarves & Gloves",
    ("apparel", "shirt"): "Shirts",
    ("apparel", "shirts"): "Shirts",
    ("apparel", "shirtsblouses"): "Shirts",
    ("apparel", "shorts"): "Shorts",
    ("apparel", "shortsleeve"): "Tops",
    ("apparel", "shortsleevetee"): "T-Shirts",
    ("apparel", "skirt"): "Skirts",
    ("apparel", "skirts"): "Skirts",
    ("apparel", "socks"): "Socks",
    ("apparel", "sockstights"): "Socks & Tights",
    ("apparel", "standardtee"): "T-Shirts",
    ("apparel", "stockings"): "Tights",
    ("apparel", "sweater"): "Sweaters",
    ("apparel", "sweaterdress"): "Knit Dress",
    ("apparel", "sweaters"): "Sweaters",
    ("apparel", "sweatpants"): "Pants",
    ("apparel", "sweats"): "Sweaters",
    ("apparel", "sweatshirt"): "Sweaters",
    ("apparel", "swim"): "Swim",
    ("apparel", "swimsuit"): "Swim",
    ("apparel", "tank"): "Tops",
    ("apparel", "tee"): "T-Shirts",
    ("apparel", "teelsprinted"): "T-Shirts",
    ("apparel", "tees"): "T-Shirts",
    ("apparel", "teessprinted"): "T-Shirts",
    ("apparel", "tights"): "Tights",
    ("apparel", "tops"): "Tops",
    ("apparel", "trousers"): "Trousers",
    ("apparel", "trousersshorts"): "Trousers",
    ("apparel", "trunks"): "Swim",
    ("apparel", "tshirt"): "T-Shirts",
    ("apparel", "tshirts"): "T-Shirts",
    ("apparel", "tunic"): "Tops",
    ("apparel", "veil"): "Veil",
    ("apparel", "vest"): "Vests",
    ("apparel", "vtgtops"): "Tops",
    ("apparel", "wideleg"): "Pants",
    ("apparel", "womensblackstyletshirt"): "Sets",
    ("apparel", "womensheathergreystyletshirt"): "Sets",
    ("apparel", "wovenlstop"): "Long Sleeve Woven Top",
    ("apparel", "wovensstop"): "Short Sleeve Woven Top",

    # Hat subcategories.
    ("hats", "accdadhat"): "Dad Hat",
    ("hats", "accsnapback"): "Snapbacks",
    ("hats", "accsnapbackhat"): "Snapback Hats",
    ("hats", "acctruckerhat"): "Trucker Hats",
    ("hats", "capbundle"): "Headwear",
    ("hats", "caps"): "Headwear",
    ("hats", "fedora"): "Headwear",
    ("hats", "handmadehats"): "Headwear",
    ("hats", "hat"): "Hats",
    ("hats", "hats"): "Hats",
    ("hats", "headwear"): "Headwear",

    # Beanie subcategories.
    ("beanies", "accknitbeanie"): "Knit Beanie",
    ("beanies", "beanie"): "Beanies",
    ("beanies", "beanies"): "Beanies",
    ("beanies", "toque"): "Beanies",

    # Bag subcategories.
    ("bags", "accshoulderbag"): "Shoulder Bags",
    ("bags", "accwovenbackpack"): "Woven Backpacks",
    ("bags", "backpack"): "Backpacks",
    ("bags", "bags"): "Bags",
    ("bags", "bagswallets"): "Wallets",
    ("bags", "coinpurse"): "Coin Purses",
    ("bags", "crossbody"): "Cross Body",
    ("bags", "duffle"): "Duffles",
    ("bags", "handbag"): "Handbags",
    ("bags", "handbags"): "Handbags",
    ("bags", "luggage"): "Luggage",
    ("bags", "messenger"): "Messenger Bags",
    ("bags", "tote"): "Totes",
    ("bags", "totebag"): "Totes",
    ("bags", "wallet"): "Wallets",
    ("bags", "weekendbag"): "Weekend Bags",

    # Footwear subcategories.
    ("footwear", "accfootwear"): "Footwear",
    ("footwear", "boots"): "Boots",
    ("footwear", "bootsbooties"): "Boots",
    ("footwear", "creepers"): "Creepers",
    ("footwear", "flats"): "Flats",
    ("footwear", "flipflop"): "Slides",
    ("footwear", "footwear"): "Footwear",
    ("footwear", "heels"): "Heels",
    ("footwear", "platformboots"): "Boots",
    ("footwear", "platforms"): "Platforms",
    ("footwear", "sandal"): "Sandals",
    ("footwear", "sandals"): "Sandals",
    ("footwear", "shoes"): "Footwear",
    ("footwear", "sneakers"): "Footwear",
    ("footwear", "wedges"): "Heels",

    # Accessory subcategories, including the shelves a store files
    # as its own top-level category.
    ("accessories", "accesory"): "miscellaneous",
    ("accessories", "accmiscellaneous"): "miscellaneous",
    ("accessories", "adapters"): "adapters",
    ("accessories", "atomizer"): "batteries & atomizers",
    ("accessories", "beads"): "jewelry",
    ("accessories", "blunttips"): "blunt supplies",
    ("accessories", "bobmarley"): "smoking accessories",
    ("accessories", "bong"): "bongs",
    ("accessories", "bowlpiece"): "bowls",
    ("accessories", "cannabuttermaker"): "silicone accessories",
    ("accessories", "case"): "storage",
    ("accessories", "chillstraw"): "pipe accessories",
    ("accessories", "chillum"): "chillum",
    ("accessories", "cleaningproducts"): "cleaning solutions",
    ("accessories", "cleaningsolutions"): "cleaning solutions",
    ("accessories", "clearsolidpipes"): "pipe accessories",
    ("accessories", "container"): "storage",
    ("accessories", "dabbingaccessories"): "wholesale accessories",
    ("accessories", "dabstraw"): "dab straws",
    ("accessories", "dabstraws"): "dab straws",
    ("accessories", "dealsdrypipes"): "pipe accessories",
    ("accessories", "dryherbpipe"): "pipe accessories",
    ("accessories", "drypipe"): "pipe accessories",
    ("accessories", "dugout"): "dugouts",
    ("accessories", "earrings"): "jewelry",
    ("accessories", "electricpipe"): "pipe accessories",
    ("accessories", "electronicdabtool"): "dab tools",
    ("accessories", "encalmodiscashcatchers"): "ash catchers",
    ("accessories", "gasmask"): "smoking accessories",
    ("accessories", "glasspipe"): "pipe accessories",
    ("accessories", "glasstip"): "glass tips",
    ("accessories", "glasstips"): "glass tips",
    ("accessories", "glycerinestraw"): "dab straws",
    ("accessories", "hairaccessories"): "hair accessories",
    ("accessories", "hairaccessory"): "hair accessories",
    ("accessories", "handpipe"): "pipe accessories",
    ("accessories", "handpipes"): "pipe accessories",
    ("accessories", "jars"): "storage",
    ("accessories", "jewelry"): "jewelry",
    ("accessories", "keychain"): "miscellaneous",
    ("accessories", "lanyard"): "miscellaneous",
    ("accessories", "lighter3pack"): "lighters",
    ("accessories", "lighterholder"): "lighters",
    ("accessories", "marbles"): "jewelry",
    ("accessories", "mousepad"): "dab mats",
    ("accessories", "mousepads"): "dab mats",
    ("accessories", "mysterymarble"): "jewelry",
    ("accessories", "necklace"): "jewelry",
    ("accessories", "necklaces"): "jewelry",
    ("accessories", "necklaceschokers"): "jewelry",
    ("accessories", "opalspheres"): "jewelry",
    ("accessories", "preparationtray"): "rolling trays",
    ("accessories", "rollingmachine"): "rolling machine",
    ("accessories", "rollingmachines"): "rolling machine",
    ("accessories", "screens"): "screens",
    ("accessories", "scrunchie"): "hair accessories",
    ("accessories", "sherlockpipe"): "pipe accessories",
    ("accessories", "siliconeaccessorykit"): "silicone accessories",
    ("accessories", "smokemiscellaneous"): "miscellaneous",
    ("accessories", "smokingaccessories"): "smoking accessories",
    ("accessories", "smokingpipe"): "pipe accessories",
    ("accessories", "solidpipes"): "pipe accessories",
    ("accessories", "spoonpipe"): "pipe accessories",
    ("accessories", "storagecontainers"): "storage",
    ("accessories", "sunglasses"): "eyewear",
    ("accessories", "terpjars"): "storage",
    ("accessories", "terppillar"): "dab tools",
    ("accessories", "terptimer"): "dab tools",
    ("accessories", "tether"): "tethers",
    ("accessories", "thedopestbattery"): "vape accessories",
    ("accessories", "tips"): "tips",
    ("accessories", "vapeaccessory"): "vape accessories",
    ("accessories", "vaporizeraccessories"): "vape accessories",
    ("accessories", "wholesaleaccessories"): "wholesale accessories",
    ("accessories", "wraps"): "wraps",
    ("accessories", "zippo"): "lighters",

    # Concentrate subcategories.
    ("concentrate", "2gliquiddiamonds"): "diamonds",
    ("concentrate", "bangerbasket"): "quartz",
    ("concentrate", "concentratesoil"): "oil",
    ("concentrate", "groundflower"): "ground flower",
    ("concentrate", "hash"): "hash",
    ("concentrate", "iceguyshash"): "hash",
    ("concentrate", "liquiddiamonds"): "diamonds",
    ("concentrate", "moonrocks"): "moonrocks",
    ("concentrate", "nectarcollector"): "quartz",
    ("concentrate", "quartzbanger"): "quartz",
    ("concentrate", "resin"): "live resin",
    ("concentrate", "slurpercaps"): "quartz",
    ("concentrate", "statichash"): "hash",
    ("concentrate", "syringe"): "applicators",
    ("concentrate", "terpsugar"): "sugar",
    ("concentrate", "thcadiamonds"): "diamonds",

    # A head shop filed cannabis hash under the Gear catch-all as "Gear ·
    # static hash" and "Gear · water hash" - sub-levels of a concentrate - and
    # the relocation table only knows the exact "Gear · hash" pairing, so the
    # sub-levels were left on a loose Gear row whose count never matched what
    # filtering to it returned. Normalise the sub to "hash" under the Gear
    # main so the relocation catches every hash spelling.
    ("gear", "statichash"): "hash",
    ("gear", "statichashs"): "hash",
    ("gear", "waterhash"): "hash",
    ("gear", "waterhashs"): "hash",
    ("gear", "iceguyshash"): "hash",
    ("gear", "hashish"): "hash",

    # Edible subcategories.
    ("edible", "bar"): "bars",
    ("edible", "beverage"): "drinks",
    ("edible", "candy"): "candy",
    ("edible", "caramel"): "candy",
    ("edible", "chews"): "chews",
    ("edible", "cookingbaking"): "cooking & baking",
    ("edible", "edible"): "Edible",
    ("edible", "gummysharks"): "gummies",
    ("edible", "seltzer"): "drinks",
    ("edible", "syrup"): "syrups",
    ("edible", "syrupbuilder3for60"): "syrups",
    ("edible", "thedopestcubesgummies"): "gummies",

    # Flower subcategories.
    ("flower", "14gramscheap"): "ounce deals",
    ("flower", "14gramssmalls"): "ounce deals",
    ("flower", "14gsmalls2pack27gpacks"): "ounce deals",
    ("flower", "2packsmalls1ounce"): "ounce deals",
    ("flower", "35gdepflowerpack"): "ounce deals",
    ("flower", "55smallsounce"): "ounce deals",
    ("flower", "7gramspremiumflower"): "premium",
    ("flower", "budlets"): "small buds",
    ("flower", "buildyourownbigspremiumounce"): "ounce deals",
    ("flower", "flowervarietypackpremium"): "premium",
    ("flower", "indoorflower"): "indoor flower",
    ("flower", "minibuds"): "small buds",
    ("flower", "mixedbuds"): "mixed buds",
    ("flower", "popcorn"): "popcorn",
    ("flower", "premiumdepflower"): "premium",
    ("flower", "premiumdepflower95ounce"): "premium",
    ("flower", "qpsmallsvarietypack"): "ounce deals",
    ("flower", "smalls"): "small buds",
    ("flower", "smallspopcorn"): "popcorn",

    # Vaporizer subcategories.
    ("vaporizers", "15gvapecartridge"): "cartridges",
    ("vaporizers", "1gthcacartridge"): "cartridges",
    ("vaporizers", "2gdualflavordisposable"): "disposables",
    ("vaporizers", "allinone"): "all-in-one",
    ("vaporizers", "briq"): "BRIQ",
    ("vaporizers", "curedresincartridge"): "cured resin cartridge",
    ("vaporizers", "curedresindisposable"): "cured resin disposable",
    ("vaporizers", "kit"): "kits",
    ("vaporizers", "kits"): "kits",
    ("vaporizers", "liveresin"): "live resin",
    ("vaporizers", "liverosin"): "live rosin",
    ("vaporizers", "liverosindisposable"): "live rosin disposable",
    ("vaporizers", "mystery1gdisposable"): "disposables",
    ("vaporizers", "pumkinpiecartandbattery"): "disposables",
    ("vaporizers", "reloadpod"): "pods",
    ("vaporizers", "stiq"): "STIQ",
    ("vaporizers", "vapecartridge"): "cartridges",
    ("vaporizers", "vapedisposable"): "disposables",

    # Pre-roll subcategories.
    ("prerolls", "preroll"): "singles",
    ("prerolls", "prerollpack"): "packs",
    ("prerolls", "singleinfusedpreroll"): "infused",

    # Topical subcategories.
    ("topicals", "bodyoil"): "body oil",
    ("topicals", "patch"): "transdermal patches",
    ("topicals", "salve"): "balms",
    ("topicals", "spray"): "sprays",
    ("topicals", "sprays"): "sprays",

    # Oral subcategories.
    ("oral", "capsules"): "capsules",
    ("oral", "tincture"): "tincture",

    # Glass subcategories.
    ("glass", "45mmbeakers"): "beakers",
    ("glass", "45mmminicollinsbeakers"): "beakers",
    ("glass", "5mmbeakers"): "beakers",
    ("glass", "5mmstraights"): "straights",
    ("glass", "7mmbeakers"): "beakers",
    ("glass", "7mmminibeaker"): "beakers",
    ("glass", "7mmscopedminibeaker"): "beakers",
    ("glass", "9mmbeakers"): "beakers",
    ("glass", "beaker"): "beakers",
    ("glass", "beakers"): "beakers",
    ("glass", "bluntbubbler"): "bongs & rigs",
    ("glass", "bongsdabrigs"): "bongs & rigs",
    ("glass", "bubblerdanklins"): "bongs & rigs",
    ("glass", "clearmodels"): "heady glass",
    ("glass", "clearmodels2nd"): "heady glass",
    ("glass", "clearslides"): "heady glass",
    ("glass", "collinsbeakers"): "beakers",
    ("glass", "colormodels"): "heady glass",
    ("glass", "danklincoil"): "downstems",
    ("glass", "downstems"): "downstems",
    ("glass", "electricbong"): "bongs & rigs",
    ("glass", "encalmodiscashcatchers"): "ash catchers",
    ("glass", "frostedbeakers"): "beakers",
    ("glass", "frostedsignaturestraights"): "beakers",
    ("glass", "fullcolorpremiumsignaturebeakers"): "beakers",
    ("glass", "fullcolorscopedbeakers"): "beakers",
    ("glass", "fullcolorsignature"): "signature series",
    ("glass", "fullsize"): "signature series",
    ("glass", "glassaccessories"): "bongs & rigs",
    ("glass", "glassattachment"): "bongs & rigs",
    ("glass", "glassbong"): "bongs & rigs",
    ("glass", "glassbubbler"): "bongs & rigs",
    ("glass", "glassrig"): "bongs & rigs",
    ("glass", "glasstop"): "bongs & rigs",
    ("glass", "glasswaterpipe"): "bongs & rigs",
    ("glass", "gravityinfuser"): "bongs & rigs",
    ("glass", "gravitypipe"): "bongs & rigs",
    ("glass", "hammers"): "hammers",
    ("glass", "headyglass"): "heady glass",
    ("glass", "heavyhitbeakers"): "beakers",
    ("glass", "hologramtoro"): "heady glass",
    ("glass", "illadelphcoils"): "illadelph glass",
    ("glass", "illadelphstraighttubes"): "illadelph glass",
    ("glass", "illadelphtubes"): "illadelph glass",
    ("glass", "percolator"): "bongs & rigs",
    ("glass", "premiumseries"): "signature series",
    ("glass", "prismhalofamfavorites"): "bongs & rigs",
    ("glass", "scopedseries"): "signature series",
    ("glass", "steamroller"): "bongs & rigs",
    ("glass", "toro"): "bongs & rigs",
    ("glass", "waterpipesrigs"): "bongs & rigs",
    ("glass", "wholesalemodels"): "wholesale models",

    # Puffco subcategories.
    ("puffco", "modl"): "modül",
    ("puffco", "modlaccessories"): "modül",
    ("puffco", "officialpuffco"): "puffco accessories",
    ("puffco", "peakattachment"): "peak attachments",
    ("puffco", "proxycore"): "proxy core",
    ("puffco", "puffcoaccessories"): "puffco accessories",
    ("puffco", "puffcoattachments"): "peak attachments",
    ("puffco", "puffcocharms"): "charms & joysticks",
    ("puffco", "puffcodrytops"): "mouthpieces",
    ("puffco", "puffcojoysticks"): "charms & joysticks",
    ("puffco", "puffcopivotmouthpieces"): "mouthpieces",
    ("puffco", "puffcoproxyattachments"): "peak attachments",

    # Kit subcategories.
    ("kits", "smartrigkit"): "rig kits",
    ("kits", "smokingkit"): "smoking kits",

    # Skate subcategories.
    ("skate", "deck"): "decks",
    ("skate", "skateboarddeck"): "decks",
    ("skate", "skater"): "skater",

    # Knitwear subcategories.
    ("knitwear", "knits"): "knits",

    # Dab mat subcategories.
    ("dabmats", "dabbingmat"): "mats",
    ("dabmats", "hexmat"): "mats",
    ("dabmats", "mousepad"): "dab mats",
    ("dabmats", "mousepads"): "dab mats",

    # Merch subcategories.
    ("merch", "boxstickers"): "stickers",
    ("merch", "diecutstickers"): "stickers",
    ("merch", "patches"): "pins & patches",
    ("merch", "pin"): "pins & patches",
    ("merch", "pinbackbuttons"): "pins & patches",
    ("merch", "posters"): "posters",
    ("merch", "stickerpack"): "stickers",

    # Misc subcategories. Sale flags, junk placeholders and home goods
    # collapse onto a handful of readable rows.
    ("misc", "2pcset"): "Bundle",
    ("misc", "archivessale"): "Sale",
    ("misc", "assurance"): "Other",
    ("misc", "bedding"): "Home & Decor",
    ("misc", "blankets"): "Home & Decor",
    ("misc", "blowout"): "Sale",
    ("misc", "bundle"): "Bundle",
    ("misc", "bundleset"): "Bundle",
    ("misc", "canvas"): "Home & Decor",
    ("misc", "carstyling"): "Car Styling",
    ("misc", "clearance"): "Sale",
    ("misc", "coasters"): "Home & Decor",
    ("misc", "collabs"): "Collabs",
    ("misc", "cup"): "Home & Decor",
    ("misc", "currentcustomdrop"): "Drops",
    ("misc", "currentdrops"): "Drops",
    ("misc", "dailydeals"): "Deals",
    ("misc", "deals"): "Deals",
    ("misc", "dealsgear"): "Deals",
    ("misc", "decor"): "Home & Decor",
    ("misc", "directsale"): "Direct Sale",
    ("misc", "drinkware"): "Home & Decor",
    ("misc", "elite"): "Other",
    ("misc", "expiviproductreplica"): "Expivi Product Replica",
    ("misc", "extensions"): "Other",
    ("misc", "extrassale"): "Sale",
    ("misc", "eyeliner"): "Beauty",
    ("misc", "eyes"): "Beauty",
    ("misc", "eyeshadow"): "Beauty",
    ("misc", "facebody"): "Beauty",
    ("misc", "fungames"): "Fun & Games",
    ("misc", "giftwithpurchase"): "Other",
    ("misc", "h"): "Other",
    ("misc", "hair"): "Beauty",
    ("misc", "highlightsection"): "Other",
    ("misc", "homeaccessory"): "Home & Decor",
    ("misc", "homestuff"): "Home & Decor",
    ("misc", "homeware"): "Home & Decor",
    ("misc", "icepackforshipping"): "Other",
    ("misc", "incense"): "Other",
    ("misc", "inflatable"): "Other",
    ("misc", "juicyjcollab"): "Collabs",
    ("misc", "kitchenbar"): "Home & Decor",
    ("misc", "lights"): "Other",
    ("misc", "lipliner"): "Beauty",
    ("misc", "lipproduct"): "Beauty",
    ("misc", "lips"): "Beauty",
    ("misc", "lipstick"): "Beauty",
    ("misc", "membership"): "Other",
    ("misc", "mirrors"): "Home & Decor",
    ("misc", "mothershipmeltdown"): "Mothership Meltdown",
    ("misc", "mug"): "Home & Decor",
    ("misc", "newproducts"): "Other",
    ("misc", "other"): "Other",
    ("misc", "othershit"): "Other",
    ("misc", "outdoor"): "Other",
    ("misc", "pallets"): "Other",
    ("misc", "pomade"): "Pomade",
    ("misc", "product"): "Other",
    ("misc", "rug"): "Home & Decor",
    ("misc", "shippingprotection"): "Other",
    ("misc", "sign"): "Other",
    ("misc", "springsale"): "Sale",
    ("misc", "tableware"): "Home & Decor",
    ("misc", "tarotcards"): "Fun & Games",
    ("misc", "towel"): "Home & Decor",
    ("misc", "toy"): "Fun & Games",
    ("misc", "umbrella"): "Other",
    ("misc", "vase"): "Home & Decor",
    ("misc", "wallpaper"): "Home & Decor",
    ("misc", "warranty"): "Other",
}

def canonical_subcategory(main: str, sub: str) -> str:
    """Rename a subcategory to its canonical form within its main category."""
    if not sub or not sub.strip():
        return ""
    alias = SUBCATEGORY_ALIASES.get((category_key(main), category_key(sub)))
    return alias or sub.strip()


# Some stores file glass under Accessories and mats under Misc/Uncategorized.
# This relocation table fixes the shelf when the (main · sub) pairing is wrong.
# Only catch-all mains (Misc, Uncategorized, Other, empty) are relocated;
# Accessories keeps its own "dab mats" subcategory.
CATEGORY_RELOCATIONS = {
    # Glass misfiled under Accessories
    category_key("Accessories \u00b7 bong"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 bongs"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 rig"): "Glass \u00b7 rigs",
    category_key("Accessories \u00b7 rigs"): "Glass \u00b7 rigs",
    category_key("Accessories \u00b7 bubbler"): "Glass \u00b7 bubblers",
    category_key("Accessories \u00b7 bubblers"): "Glass \u00b7 bubblers",
    category_key("Accessories \u00b7 waterpipe"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 waterpipes"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 glasspipe"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 glasspipes"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 pipe"): "Glass \u00b7 bongs",
    category_key("Accessories \u00b7 pipes"): "Glass \u00b7 bongs",
    # Glass accessories (caps, bangers, nails) misfiled under Accessories → Glass → Gear
    category_key("Accessories \u00b7 cap"): "Glass \u00b7 caps",
    category_key("Accessories \u00b7 caps"): "Glass \u00b7 caps",
    category_key("Accessories \u00b7 banger cap"): "Glass \u00b7 banger caps",
    category_key("Accessories \u00b7 spinner cap"): "Glass \u00b7 spinner caps",
    category_key("Accessories \u00b7 carb cap"): "Glass \u00b7 carb caps",
    category_key("Accessories \u00b7 directional cap"): "Glass \u00b7 directional caps",
    category_key("Accessories \u00b7 dab cap"): "Glass \u00b7 dab caps",
    category_key("Accessories \u00b7 bubble cap"): "Glass \u00b7 bubble caps",
    category_key("Accessories \u00b7 banger"): "Glass \u00b7 bangers",
    category_key("Accessories \u00b7 nail"): "Glass \u00b7 nails",
    category_key("Accessories \u00b7 bucket"): "Glass \u00b7 bangers",
    # Dab mats misfiled under catch-all shelves (Misc, Uncategorized, Other)
    category_key("Misc \u00b7 mat"): "Dab Mats",
    category_key("Misc \u00b7 mats"): "Dab Mats",
    category_key("Misc \u00b7 dabmat"): "Dab Mats",
    category_key("Misc \u00b7 dabmats"): "Dab Mats",
    category_key("Misc \u00b7 dab-mat"): "Dab Mats",
    category_key("Misc \u00b7 dab-mats"): "Dab Mats",
    category_key("Misc \u00b7 dabpad"): "Dab Mats",
    category_key("Misc \u00b7 dabpads"): "Dab Mats",
    category_key("Uncategorized \u00b7 mat"): "Dab Mats",
    category_key("Uncategorized \u00b7 mats"): "Dab Mats",
    category_key("Uncategorized \u00b7 dabmat"): "Dab Mats",
    category_key("Uncategorized \u00b7 dabmats"): "Dab Mats",
    category_key("Uncategorized \u00b7 dab-mat"): "Dab Mats",
    category_key("Uncategorized \u00b7 dab-mats"): "Dab Mats",
    category_key("Other \u00b7 mat"): "Dab Mats",
    category_key("Other \u00b7 mats"): "Dab Mats",
    category_key("Other \u00b7 dabmat"): "Dab Mats",
    category_key("Other \u00b7 dabmats"): "Dab Mats",
    # Cannabis concentrates a head shop filed under the Gear catch-all. Hash,
    # quartz and diamonds are concentrates however a store spells the shelf, so
    # the pair is wrong (Gear is hardware) rather than the sub alone: without
    # this the products land on a loose Gear row whose count (7) never matches
    # what filtering to that row returns (0), because the filter resolves the
    # bare sub to its cannabis main.
    category_key("Gear \u00b7 hash"): "Concentrate \u00b7 hash",
    category_key("Gear \u00b7 quartz"): "Concentrate \u00b7 quartz",
    category_key("Gear \u00b7 diamonds"): "Concentrate \u00b7 diamonds",
}

# Shelf redesign group remap, applied after alias resolution so it cannot be
# overridden by a store's raw spelling:
#   Glass → Gear      (glass art renamed to the broader "gear" shelf)
#   Puffco → Gear     (Puffco hardware is gear, not cannabis)
#   Dab Mats → Gear   (silicone mats sit beside the glass)
#   Kits → Gear       (smoking kits are gear)
#   Misc → Gear       (most of the catch-all is glass/gear)
#   Skate → Clothing  (skate decks are apparel-adjacent)
#   Merch → Clothing  (pins, patches, branded merch → clothing)
MAIN_REMAP = {
    "puffco": "Gear",
    "skate": "Clothing",
    "misc": "Gear",
    "dabmats": "Gear",
    "glass": "Gear",
    "merch": "Clothing",
    "kits": "Gear",
}

# Stores whose "Vaporizers" shelf holds prefilled cannabis (stays in Cannabis).
# Stores whose "Vaporizers" shelf holds empty/reusable hardware (moves to Gear).
# Classified by scraper type: dutchie/sweed are dispensary POS (cannabis);
# shopify/bigcartel/magento/woocommerce/fourthwall are ecommerce (hardware).
CANNABIS_VAPE_SCRAPERS = {"dutchie", "sweed"}

_STORE_SCRAPER_CACHE: Dict[str, Optional[str]] = {}


def _store_scraper(store_id: str) -> Optional[str]:
    """The scraper type for a store, lazily loaded from config.yaml and cached.

    Returns None for stores not in config.yaml (e.g. test fixtures), in which
    case the vape shelf is left untouched rather than guessed at.
    """
    if store_id not in _STORE_SCRAPER_CACHE:
        try:
            cfg = Config.load(str(Path(__file__).resolve().parent.parent / "config.yaml"))
            store = cfg.get_store(store_id)
            _STORE_SCRAPER_CACHE[store_id] = store.scraper if store else None
        except Exception:
            _STORE_SCRAPER_CACHE[store_id] = None
    return _STORE_SCRAPER_CACHE[store_id]


# Phenotype notation in product titles: a dispensary labels its cannabis by
# its I/S/H type, and that is the store's own word for the product, so it beats
# the shelf it was filed under. Mirrors the dashboard's STRAIN_NAME_PATTERNS.
_STRAIN_NAME_PATTERNS = [
    (re.compile(r"\(?\s*\[\s*s(?:ativa)?\s*\]\s*\)?", re.IGNORECASE), "sativa"),
    (re.compile(r"\(?\s*\[\s*i(?:ndica)?\s*\]\s*\)?", re.IGNORECASE), "indica"),
    (re.compile(r"\(?\s*\[\s*h(?:ybrid)?\s*\]\s*\)?", re.IGNORECASE), "hybrid"),
    (re.compile(r"\(\s*s\s*\)", re.IGNORECASE), "sativa"),
    (re.compile(r"\(\s*i\s*\)", re.IGNORECASE), "indica"),
    (re.compile(r"\(\s*h\s*\)", re.IGNORECASE), "hybrid"),
    (re.compile(r"\(\s*sativa\s*\)", re.IGNORECASE), "sativa"),
    (re.compile(r"\(\s*indica\s*\)", re.IGNORECASE), "indica"),
    (re.compile(r"\(\s*hybrid\s*\)", re.IGNORECASE), "hybrid"),
    (re.compile(r"[\s\-]\s*s(?:ativa)?\s*$", re.IGNORECASE), "sativa"),
    (re.compile(r"[\s\-]\s*i(?:ndica)?\s*$", re.IGNORECASE), "indica"),
    (re.compile(r"[\s\-]\s*h(?:ybrid)?\s*$", re.IGNORECASE), "hybrid"),
    (re.compile(r"\b[ISH]\/\s*s\b", re.IGNORECASE), "sativa"),
    (re.compile(r"\b[ISH]\/\s*i\b", re.IGNORECASE), "indica"),
    (re.compile(r"\b[ISH]\/\s*h\b", re.IGNORECASE), "hybrid"),
    (re.compile(r"\bsativa\b", re.IGNORECASE), "sativa"),
    (re.compile(r"\bindica\b", re.IGNORECASE), "indica"),
    (re.compile(r"\bhybrid\b", re.IGNORECASE), "hybrid"),
]


def _strain_type_from_name(name: str) -> str:
    """Return the phenotype a product title states, or '' when it is silent.

    A store's own label for the product is more trustworthy than the shelf it
    was filed under, so this is checked before any hardware/scraper heuristic.
    """
    if not name:
        return ""
    for pattern, type_ in _STRAIN_NAME_PATTERNS:
        if pattern.search(name):
            return type_
    return ""


# Hardware vape brands that belong on Gear even when a dispensary sells them.
VAPE_HARDWARE_BRANDS = {
    "puffco", "focusv", "focus v", "drdabber", "dr dabber",
    "pulsar", "gpen", "g pen", "kvnthd", "kvlthd", "linx",
    "boundary", "dr dabber",
}


def _is_hardware_brand(brand: str) -> bool:
    if not brand:
        return False
    key = category_key(brand)
    return key in VAPE_HARDWARE_BRANDS or any(
        b in key for b in ("puffco", "focusv", "drdabber", "pulsar", "gpen")
    )


def _vape_remap(
    canonical: str,
    store_id: str | None = None,
    brand: str | None = None,
    name: str = "",
) -> str:
    """Move empty/reusable vaporizers from head shops onto the Gear shelf.

    Prefilled cannabis vapes from dispensaries stay in the Cannabis section;
    the same ``Vaporizers`` main from a head shop is hardware and belongs on
    Gear. A known hardware brand (Puffco, Focus V, ...) always lands on Gear,
    even at a dispensary that also sells prefilled cannabis cartridges.
    Hardware brands filed under ``Concentrates`` are glass/gear, not cannabis,
    and are moved to Gear as well. Returns ``canonical`` unchanged when the
    main is neither ``Vaporizers`` nor ``Concentrate``.

    A product whose title states its I/S/H type is cannabis no matter what
    shelf or brand it carries: a Puffco-branded cartridge labelled "Indica" is
    a filled vape, not a device, so it stays in Cannabis. The name is the
    store's own word for the product and beats both the shelf and the brand.
    """
    if canonical not in ("Vaporizers", "Concentrate"):
        return canonical
    if _strain_type_from_name(name):
        return canonical
    # Hardware brands always go to Gear, regardless of store type.
    if _is_hardware_brand(brand):
        return "Gear"
    if canonical == "Concentrate":
        return canonical
    if store_id is None:
        return canonical
    scraper = _store_scraper(store_id)
    # Unknown stores (e.g. test fixtures) are not remapped: we only move a
    # vaporizer to Gear when we know it is a head shop.
    if scraper is None:
        return canonical
    if scraper in CANNABIS_VAPE_SCRAPERS:
        return "Vaporizers"
    return "Gear"
    if canonical == "Concentrate":
        return canonical
    if store_id is None:
        return canonical
    scraper = _store_scraper(store_id)
    # Unknown stores (e.g. test fixtures) are not remapped: we only move a
    # vaporizer to Gear when we know it is a head shop.
    if scraper is None:
        return canonical
    if scraper in CANNABIS_VAPE_SCRAPERS:
        return "Vaporizers"
    return "Gear"


def canonical_category(
    category: str,
    store_id: str | None = None,
    brand: str | None = None,
    name: str = "",
) -> str:
    """Return the category renamed to its canonical main category.

    The subcategory is canonicalised too, because that is where stores disagree
    most: an infused pre-roll pack is the same shelf however it is spelled.

    ``name`` is the product title; when it states an I/S/H type that product is
    cannabis no matter what shelf or brand it carries, so it is passed through
    to the vaporizer remap. It is optional and defaults to empty so the old
    single-argument contract is preserved.
    """
    if not category or not category.strip():
        return category

    # A store sometimes files a shelf under the wrong group: bongs and glassware
    # land under Accessories while the Glass group holds the rest of them, and
    # the silicone mats turn up both as an Accessories row and as a group of
    # their own. Neither the main nor the sub alone can express that, because
    # each is individually correct and only the pairing is wrong.
    # Normalise the sub before the relocation lookup: a store filed "Gear ·
    # static hash" and "Gear · water hash" - sub-levels of a concentrate - and
    # the relocation table only knows the exact "Gear · hash" pairing, so the
    # sub-levels were left on a loose Gear row whose count never matched what
    # filtering to it returned. Normalising the sub first lets the relocation
    # catch every hash spelling.
    pre_main = main_category(category)
    pre_sub = canonical_subcategory(pre_main, sub_category(category))
    pre_canonical = f"{pre_main}{SUB_SEPARATOR}{pre_sub}" if pre_sub else pre_main
    relocation = CATEGORY_RELOCATIONS.get(category_key(pre_canonical))
    if relocation:
        return _vape_remap(relocation, store_id, brand, name)

    main = main_category(category)
    key = category_key(main)
    canonical = CATEGORY_ALIASES.get(key, main)

    # Shelf redesign: remap canonical mains to the new sections.
    canonical = MAIN_REMAP.get(category_key(canonical), canonical)
    canonical = _vape_remap(canonical, store_id, brand, name)

    sub = canonical_subcategory(canonical, sub_category(category))
    return f"{canonical}{SUB_SEPARATOR}{sub}" if sub else canonical


# Some stores file a dab mat under a catch-all shelf ("misc", "Uncategorized")
# with no subcategory to key off, so canonical_category alone leaves it on the
# wrong shelf. When the canonical main is a catch-all and the product title
# names a mat, it is moved onto the Dab Mats shelf. This and the title-based
# subcategory inference below are kept separate from canonical_category so that
# function keeps its single-argument contract and its existing behaviour.
_CATCH_ALL_MAINS = {"", "misc", "uncategorized", "other"}
_DAB_MAT_NAME_RE = re.compile(
    r"\b(dab\s*-?\s*mats?|dab\s*-?\s*pads?|dabbing\s+mat)\b",
    re.IGNORECASE,
)
# A mousepad is moved onto the Dab Mats shelf whatever shelf the store
# filed it under, because the glass and accessory vendors list the
# silicone sheets beside their other stock.
_MOUSEPAD_NAME_RE = re.compile(
    r"\bmouse\s*-?\s*pads?\b",
    re.IGNORECASE,
)
# A mousepad is moved onto the Dab Mats shelf whatever shelf the store
# filed it under, because the glass and accessory vendors list the
# silicone sheets beside their other stock.
_MOUSEPAD_NAME_RE = re.compile(
    r"\bmouse\s*-?\s*pads?\b",
    re.IGNORECASE,
)
# A mousepad is moved onto the Dab Mats shelf whatever shelf the store
# filed it under, because the glass and accessory vendors list the
# silicone sheets beside their other stock.
_MOUSEPAD_NAME_RE = re.compile(
    r"\bmouse\s*-?\s*pads?\b",
    re.IGNORECASE,
)

# A cap (carb cap, bubble cap, slurper cap, maria cap, ...) is always a
# glass accessory; route it onto Gear wherever the store filed it.
# Only matches dab/glass cap types, not fashion hats (trucker cap, etc.).
_CAP_NAME_RE = re.compile(
    r"\b(carb|bubble|spinner|spin|directional|slurper|dab|marble|maria|marios|terp|banger)\s+cap\b",
    re.IGNORECASE,
)


def _subcategory_patterns() -> Dict[str, list]:
    """Match keys for each canonical main's known subcategories.

    The subcategory alias keys already encode the singular, plural and unhyphen
    spellings a store might type, so they are reused directly as match keys.
    The longest match wins so the most specific shelf is chosen.
    """
    index: Dict[str, list] = {}
    for (main_key, sub_alias), canonical in SUBCATEGORY_ALIASES.items():
        key = category_key(sub_alias)
        if key:
            index.setdefault(main_key, []).append((key, canonical))
    for entries in index.values():
        entries.sort(key=lambda kv: len(kv[0]), reverse=True)
    return index


_SUBCATEGORY_PATTERNS = _subcategory_patterns()


def infer_subcategory(main: str, name: str) -> str:
    """The known subcategory named in a product title, or "" for none.

    Only the subcategories curated for ``main`` are considered, matched as
    whole keys inside the de-spaced title, so a shelf that merely shares a few
    letters is not chosen. Returns "" when the title gives no confident shelf,
    leaving the product on its main category.
    """
    if not name:
        return ""
    entries = _SUBCATEGORY_PATTERNS.get(category_key(main))
    if not entries:
        return ""
    title_key = category_key(name)
    for key, canonical in entries:
        if key in title_key:
            return canonical
    return ""


# The shelves that fold into the "Gear" section. Each keeps its own name on the
# dashboard so a browser can jump straight to the bongs or the Puffco Peak
# instead of wading through one giant Gear row; the section divider is what
# groups them. canonical_category_named unpacks a "Gear · <sub>" pair back to
# "<sub>" so the frontend never has to special-case the collapsed main.
GEAR_SUBCATEGORIES = {
    "glass", "puffco", "dabmats", "kits", "misc",
}


def canonical_category_named(
    category: str,
    name: str = "",
    store_id: str | None = None,
    brand: str | None = None,
) -> str:
    """canonical_category, plus two title-based corrections.

    1. A dab mat filed under "misc" (no subcategory) cannot be recovered from
       the category string alone, so its title moves it onto the Gear shelf
       (dab mats are now part of Gear).
    2. When the canonical category has no subcategory but the product title
       names a known subcategory for that main, that subcategory is attached,
       so a store with no taxonomy still lands on the right shelf.
    """
    result = canonical_category(category, store_id, brand, name)
    if not name:
        return result

    main = main_category(result)
    main_key = category_key(main)

    # A catch-all shelf is never right for any product, but a mat can be
    # recovered from its title; anything else on a catch-all stays put.
    if main_key in _CATCH_ALL_MAINS:
        if _DAB_MAT_NAME_RE.search(name) or _MOUSEPAD_NAME_RE.search(name):
            return "Gear"
        return result

    # A mousepad is a dab mat whichever shelf the store filed it under, so it
    # is moved onto Gear rather than left scattered beside the glass and the
    # accessories. Only this spelling is force-moved: "dab mat" and "dab pad"
    # already have shelves of their own, and pulling a "Dab Pad" out of
    # Concentrates would relocate a genuine product.
    if main_key != "dabmats" and _MOUSEPAD_NAME_RE.search(name):
        return "Gear"

    # A cap (carb cap, bubble cap, slurper cap, ...) is always a glass
    # accessory; route it onto Gear wherever the store filed it.
    if _CAP_NAME_RE.search(name) and main_key != "gear":
        return "Gear"

    # Only add a subcategory when none is already present.
    if SUB_SEPARATOR not in result:
        sub = infer_subcategory(main, name)
        if sub:
            return f"{main}{SUB_SEPARATOR}{sub}"
    return result


def is_canonical(category: str) -> bool:
    """True when the category already uses its canonical main category."""
    return canonical_category(category) == category
