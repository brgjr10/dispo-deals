- [x] add graphs for deals to show best categories or brands
- [x] add clean annimations to all of the ui elements without impacting performance
- [x] integrate leafly strain data importing per product strain
- [x] add location permission that will automatically show every dispensary's products based on a user set mile radius instead of hard coding stores - this should be fetched from dutchie somehow
  - **Blocked:** Dutchie's `filteredDispensaries` GraphQL query matches `cNameOrID`
    **exactly only**. Verified against the live API: its `city`, `state`,
    `zipCode`, `country` and `radius` filter fields exist in
    `dispensariesFilterInput` but return **0 results for every value tried**,
    including exact values read back from a known dispensary's own
    `location { city state country }`. A `cName` prefix match also fails. There
    is no coordinate filter at all, so "dispensaries within N miles of my
    location" cannot be asked of this API.
  - **Shipped instead:** **Add Store by URL** (`Add Store` button in the header).
    Paste any Dutchie store link and it is resolved through the working exact
    `cNameOrID` lookup, scraped, and added to the dashboard — replacing
    hard-coded stores in `config.yaml` with ones added at runtime. Stores are
    persisted in the `known_stores` table, so they survive a restart.
  - To finish the radius feature Dutchie would need to expose a location search,
    or the app would need a third-party dispensary directory plus a reverse
    geocoder to turn coordinates into a city/state.
- [x] send a rich webhook message per store listing the best deals and the overall menu
- [x] only notify when a deal is genuinely new (re-notify only on a deeper discount)
- [x] weekly menu digest with new/carryover markers, sent once per week per store
