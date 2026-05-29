const RACE_PACE_DATA_PATH = "C:\\Users\\hfaur\\AppData\\Roaming\\race-pace-career-app";
const CARS_CSV_PATH = "../../src/circuit_stackers/data/Cars.csv";
const DB_NAME_RE = /^rxdb-dexie-(career-sim-(?:main-db|slot-\d+))--\d+--([A-Za-z0-9_-]+)$/i;
const RELATION_COLLECTIONS = ["championshipSeasons", "championshipEntry", "teamSeats", "driverContracts"];
const PLAYER_SIGNAL_COLLECTIONS = ["gameStates", "championshipEntry", "teamSeats", "driverContracts", "_rxdb_internal"];
const DRIVER_ID_KEY_HINTS = [
  "driverid",
  "driver_id",
  "assigneddriverid",
  "occupantdriverid",
  "reservedriverid",
  "primarydriverid",
  "secondarydriverid",
];
const COLOR_SETS = [
  "FFFFFF,000000,FFFFFF",
  "E10600,000000,FFFFFF",
  "005AFF,FFFFFF,000000",
  "FFD700,000000,1C1C1C",
  "00AEEF,FFFFFF,003366",
  "FF6600,000000,FFFFFF",
  "2E8B57,FFFFFF,000000",
  "800020,FFFFFF,000000",
];

const state = {
  bundle: new Map(),
  cars: [],
  slotKeys: [],
  championshipOptions: [],
  playerProfiles: new Map(),
};

const dataPathInput = document.getElementById("dataPath");
const slotSelect = document.getElementById("slotSelect");
const championshipSelect = document.getElementById("championshipSelect");
const playerSelect = document.getElementById("playerSelect");
const carSelect = document.getElementById("carSelect");
const refreshButton = document.getElementById("refreshButton");
const exportButton = document.getElementById("exportButton");
const statusNode = document.getElementById("status");
const summaryNode = document.getElementById("summary");

dataPathInput.value = RACE_PACE_DATA_PATH;

refreshButton.addEventListener("click", refreshData);
slotSelect.addEventListener("change", onSlotChange);
championshipSelect.addEventListener("change", onChampionshipChange);
playerSelect.addEventListener("change", onPlayerChange);
exportButton.addEventListener("click", exportRoster);

await initialize();

async function initialize() {
  setStatus("Loading iRacing car list and scanning IndexedDB...");
  state.cars = await loadIracingCars();
  populateCarSelect();
  await refreshData();
}

async function refreshData() {
  try {
    setStatus("Scanning Race Pace IndexedDB databases...");
    const bundle = await scanBundle();
    state.bundle = bundle;
    state.slotKeys = Array.from(bundle.keys()).sort((left, right) => {
      if (left === "career-sim-main-db") return -1;
      if (right === "career-sim-main-db") return 1;
      return left.localeCompare(right);
    });
    populateSlotSelect();
    onSlotChange();
    setStatus(`Loaded ${state.slotKeys.length} save slot profile(s).`);
  } catch (error) {
    state.bundle = new Map();
    state.slotKeys = [];
    state.championshipOptions = [];
    populateSlotSelect();
    populateChampionshipSelect();
    setSummary(String(error.message || error));
    setStatus(String(error.message || error), true);
  }
}

async function scanBundle() {
  if (!indexedDB.databases) {
    throw new Error("This browser does not expose indexedDB.databases(). Launch the app with the provided launcher.");
  }

  const databases = await indexedDB.databases();
  const named = databases
    .map((entry) => String(entry.name || "").trim())
    .filter(Boolean);

  const matched = named
    .map((name) => {
      const match = name.match(DB_NAME_RE);
      return match ? { name, slotKey: match[1], collection: match[2] } : null;
    })
    .filter(Boolean);

  if (!matched.length) {
    throw new Error(
      "No Race Pace RxDB databases were found. Make sure the launcher opened this page against C:\\Users\\hfaur\\AppData\\Roaming\\race-pace-career-app and that Race Pace has been opened on this machine."
    );
  }

  const bundle = new Map();
  for (const { name, slotKey, collection } of matched) {
    const docs = await readDocsStore(name);
    if (!bundle.has(slotKey)) {
      bundle.set(slotKey, new Map());
    }
    bundle.get(slotKey).set(collection, docs);
  }
  return bundle;
}

function populateSlotSelect() {
  slotSelect.innerHTML = "";
  if (!state.slotKeys.length) {
    slotSelect.append(new Option("No slots found", ""));
    return;
  }
  for (const slotKey of state.slotKeys) {
    slotSelect.append(new Option(slotLabel(slotKey), slotKey));
  }
}

function onSlotChange() {
  const slotKey = slotSelect.value;
  state.playerProfiles.set(slotKey, resolvePlayerProfile(slotKey));
  state.championshipOptions = listChampionshipOptions(slotKey);
  populateChampionshipSelect();
  onChampionshipChange(false);
}

function populateChampionshipSelect() {
  championshipSelect.innerHTML = "";
  if (!state.championshipOptions.length) {
    championshipSelect.append(new Option("No championships found", ""));
    return;
  }
  for (const option of state.championshipOptions) {
    championshipSelect.append(new Option(option.label, option.championshipId));
  }
}

function onChampionshipChange(preservePlayerSelection = true) {
  const option = selectedChampionship();
  if (!option) {
    setSummary("No championship selected.");
    return;
  }

  const autoCar = inferIracingCar(option);
  selectCar(autoCar);

  const lines = [
    `Race Pace Data Folder: ${RACE_PACE_DATA_PATH}`,
    `Slot: ${slotLabel(option.slotKey)}`,
    `Championship: ${option.label}`,
    `Championship ID: ${option.championshipId}`,
    `Season IDs: ${option.seasonIds.length ? option.seasonIds.join(", ") : "Not found"}`,
  ];
  const playerProfile = state.playerProfiles.get(option.slotKey) || resolvePlayerProfile(option.slotKey);
  const currentPlayerSelection = preservePlayerSelection ? playerSelect.value : "__auto__";
  populatePlayerSelect(option, playerProfile, currentPlayerSelection);
  if (playerProfile.names.size) {
    lines.push(`Detected Player Name: ${Array.from(playerProfile.names).join(" | ")}`);
  }
  const selectedPlayerName = selectedPlayerDriverName();
  if (selectedPlayerName) {
    lines.push(`Selected Player Driver: ${denormalizePersonName(selectedPlayerName)}`);
  }

  try {
    const playerDriverIds = resolvePlayerDriverIds(option);
    const drivers = resolveRosterDrivers(option);
    lines.push(`Resolved Drivers: ${drivers.length}`);
    lines.push(`Detected Player Drivers: ${playerDriverIds.size}`);
    lines.push(`First Drivers: ${drivers.slice(0, 6).map(bestDriverName).join(", ")}`);
  } catch (error) {
    lines.push(`Driver resolution warning: ${String(error.message || error)}`);
  }

  lines.push(`Auto Car Match: ${autoCar ? carLabel(autoCar) : "None"}`);
  setSummary(lines.join("\n"));
}

function onPlayerChange() {
  onChampionshipChange(true);
}

async function exportRoster() {
  try {
    const option = selectedChampionship();
    if (!option) {
      throw new Error("Choose a championship first.");
    }
    const playerProfile = state.playerProfiles.get(option.slotKey) || resolvePlayerProfile(option.slotKey);
    const selectedPlayerName = selectedPlayerDriverName();
    const playerDriverIds = resolvePlayerDriverIds(option);
    const drivers = resolveRosterDrivers(option).filter((driver) => {
      const driverId = docId(driver);
      if (playerDriverIds.has(driverId)) return false;
      const normalizedName = normalizePersonName(bestDriverName(driver));
      if (normalizedName && playerProfile.names.has(normalizedName)) return false;
      if (normalizedName && selectedPlayerName && normalizedName === selectedPlayerName) return false;
      return true;
    });
    const car = selectedCar(option);
    const payload = buildRosterPayload(drivers, car);
    downloadJson(`AMS2-${slugify(slotLabel(option.slotKey))}-${slugify(option.label)}-roster.json`, payload);
    setStatus(`Exported ${payload.drivers.length} drivers for ${option.label}.`);
    setSummary(
      [
        `Export complete for ${option.label}`,
        `Slot: ${slotLabel(option.slotKey)}`,
        `Drivers: ${payload.drivers.length}`,
        `Excluded Player Drivers: ${playerDriverIds.size}`,
        `Detected Player Name: ${Array.from(playerProfile.names).join(" | ") || "None"}`,
        `Selected Player Driver: ${selectedPlayerName || "None"}`,
        `Car: ${car ? carLabel(car) : "None"}`,
      ].join("\n")
    );
  } catch (error) {
    setStatus(String(error.message || error), true);
  }
}

function listChampionshipOptions(slotKey) {
  const collections = state.bundle.get(slotKey) || new Map();
  const championships = collections.get("championships") || [];
  const seasons = collections.get("championshipSeasons") || [];
  const entries = collections.get("championshipEntry") || [];

  const seasonIdsByChampionship = new Map();
  for (const season of seasons) {
    const seasonId = docId(season);
    for (const championshipId of championshipReferenceValues(season)) {
      if (!seasonId) continue;
      if (!seasonIdsByChampionship.has(championshipId)) {
        seasonIdsByChampionship.set(championshipId, new Set());
      }
      seasonIdsByChampionship.get(championshipId).add(seasonId);
    }
  }

  const options = new Map();
  for (const doc of championships) {
    const championshipId = bestChampionshipId(doc);
    if (!championshipId) continue;
    options.set(championshipId, {
      slotKey,
      championshipId,
      label: bestChampionshipLabel(doc),
      seasonIds: Array.from(seasonIdsByChampionship.get(championshipId) || []).sort(),
      sourceDoc: doc,
    });
  }

  if (!options.size) {
    for (const season of seasons) {
      const seasonRefs = Array.from(championshipReferenceValues(season));
      const championshipId = seasonRefs[0] || docId(season);
      if (!championshipId || options.has(championshipId)) continue;
      const seasonId = docId(season);
      options.set(championshipId, {
        slotKey,
        championshipId,
        label: bestChampionshipLabel(season),
        seasonIds: seasonId ? [seasonId] : [],
        sourceDoc: season,
      });
    }
  }

  if (!options.size) {
    for (const entry of entries) {
      const refs = Array.from(championshipReferenceValues(entry));
      const championshipId = refs[0];
      if (!championshipId || options.has(championshipId)) continue;
      options.set(championshipId, {
        slotKey,
        championshipId,
        label: bestChampionshipLabel(entry),
        seasonIds: [],
        sourceDoc: entry,
      });
    }
  }

  return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label));
}

function resolveRosterDrivers(option) {
  const collections = state.bundle.get(option.slotKey) || new Map();
  const drivers = collections.get("drivers") || [];
  if (!drivers.length) {
    throw new Error(`No drivers collection was found for ${slotLabel(option.slotKey)}.`);
  }

  const refs = new Set([option.championshipId, ...option.seasonIds]);
  const matched = new Set();
  const driverIds = new Set();

  let changed = true;
  while (changed) {
    changed = false;
    for (const collectionName of RELATION_COLLECTIONS) {
      for (const doc of collections.get(collectionName) || []) {
        const key = `${collectionName}:${docId(doc) || JSON.stringify(doc).slice(0, 60)}`;
        if (matched.has(key)) continue;
        if (!docReferencesAny(doc, refs)) continue;
        matched.add(key);
        const relationRefs = relationValues(doc);
        const newRelationRefs = [...relationRefs].filter((value) => !refs.has(value));
        const newDriverIds = [...driverReferenceValues(doc)].filter((value) => !driverIds.has(value));
        for (const value of relationRefs) refs.add(value);
        for (const value of driverReferenceValues(doc)) driverIds.add(value);
        if (newRelationRefs.length || newDriverIds.length) {
          changed = true;
        }
      }
    }
  }

  if (!driverIds.size) {
    for (const entry of collections.get("championshipEntry") || []) {
      if (docReferencesAny(entry, refs)) {
        for (const value of driverReferenceValues(entry)) {
          driverIds.add(value);
        }
      }
    }
  }

  if (!driverIds.size) {
    throw new Error(
      `Could not resolve assigned drivers for ${option.label}. Close Race Pace and try refreshing so the browser can read the profile cleanly.`
    );
  }

  const driversById = new Map(drivers.map((driver) => [docId(driver), driver]));
  return Array.from(driverIds)
    .map((driverId) => driversById.get(driverId))
    .filter(Boolean)
    .sort((left, right) => bestDriverName(left).localeCompare(bestDriverName(right)));
}

function populatePlayerSelect(option, playerProfile, preferredSelection = "__auto__") {
  playerSelect.innerHTML = "";
  playerSelect.append(new Option("Auto-detect / none", "__auto__"));

  const added = new Set();
  for (const detectedName of Array.from(playerProfile.names).sort()) {
    const label = denormalizePersonName(detectedName);
    playerSelect.append(new Option(`Detected: ${label}`, detectedName));
    added.add(detectedName);
  }

  try {
    const drivers = resolveRosterDrivers(option);
    for (const driver of drivers) {
      const displayName = bestDriverName(driver);
      const normalizedName = normalizePersonName(displayName);
      if (!normalizedName || added.has(normalizedName)) continue;
      playerSelect.append(new Option(displayName, normalizedName));
      added.add(normalizedName);
    }
  } catch (_error) {
    // Leave only auto/detected names when roster drivers are unavailable.
  }

  if (preferredSelection && preferredSelection !== "__auto__" && added.has(preferredSelection)) {
    playerSelect.value = preferredSelection;
    return;
  }

  const detectedDefault = Array.from(playerProfile.names)[0];
  playerSelect.value = detectedDefault && added.has(detectedDefault) ? detectedDefault : "__auto__";
}

function selectedPlayerDriverName() {
  const value = playerSelect.value;
  return value && value !== "__auto__" ? value : "";
}

function resolvePlayerDriverIds(option) {
  const collections = state.bundle.get(option.slotKey) || new Map();
  const refs = new Set([option.championshipId, ...option.seasonIds]);
  const playerDriverIds = new Set();
  const playerProfile = state.playerProfiles.get(option.slotKey) || resolvePlayerProfile(option.slotKey);
  const playerNames = new Set(playerProfile.names);

  for (const collectionName of PLAYER_SIGNAL_COLLECTIONS) {
    for (const doc of collections.get(collectionName) || []) {
      if (!looksPlayerRelated(doc, refs)) continue;
      for (const driverId of playerDriverReferenceValues(doc)) {
        playerDriverIds.add(driverId);
      }
      for (const name of playerNameCandidates(doc)) {
        playerNames.add(name);
      }
    }
  }

  for (const driver of collections.get("drivers") || []) {
    if (docLooksPlayer(driver)) {
      const id = docId(driver);
      if (id) playerDriverIds.add(id);
    }
    const normalizedDriverName = normalizePersonName(bestDriverName(driver));
    if (normalizedDriverName && playerNames.has(normalizedDriverName)) {
      const id = docId(driver);
      if (id) playerDriverIds.add(id);
    }
  }

  return playerDriverIds;
}

function resolvePlayerProfile(slotKey) {
  const collections = state.bundle.get(slotKey) || new Map();
  const names = new Set();
  const ids = new Set();

  for (const collectionName of PLAYER_SIGNAL_COLLECTIONS) {
    for (const doc of collections.get(collectionName) || []) {
      if (!doc || typeof doc !== "object") continue;

      for (const driverId of playerDriverReferenceValues(doc)) {
        ids.add(driverId);
      }

      if (docLooksPlayer(doc) || hasPlayerNameSignals(doc)) {
        for (const name of playerNameCandidates(doc)) {
          if (name) names.add(name);
        }
      }

      for (const [key, value] of Object.entries(doc)) {
        const normalized = normalizeKey(key);
        if (!normalized.includes("player")) continue;
        if (value && typeof value === "object") {
          for (const name of playerNameCandidates(value)) {
            if (name) names.add(name);
          }
          for (const driverId of playerDriverReferenceValues(value)) {
            ids.add(driverId);
          }
        }
      }
    }
  }

  for (const driver of collections.get("drivers") || []) {
    const id = docId(driver);
    if (id && ids.has(id)) {
      const name = normalizePersonName(bestDriverName(driver));
      if (name) names.add(name);
    }
    if (docLooksPlayer(driver)) {
      const name = normalizePersonName(bestDriverName(driver));
      if (name) names.add(name);
      if (id) ids.add(id);
    }
  }

  return { names, ids };
}

function buildRosterPayload(drivers, car) {
  return {
    drivers: drivers.map((driver, index) => {
      const colors = pick(COLOR_SETS);
      const skill = pctValue(valueForKeys(driver, ["race_skill", "raceSkill", "skill"]));
      const aggression = pctValue(valueForKeys(driver, ["aggression"]));
      const consistency = pctValue(valueForKeys(driver, ["consistency"]));
      const stamina = pctValue(valueForKeys(driver, ["stamina"]));
      const fuelManagement = pctValue(valueForKeys(driver, ["fuel_management", "fuelManagement"]));
      const tyreManagement = pctValue(valueForKeys(driver, ["tyre_management", "tire_management", "tyreManagement", "tireManagement"]));
      const strategyRiskiness = pctValue(
        valueForKeys(driver, [
          "avoidance_of_forced_mistakes",
          "avoidanceOfForcedMistakes",
          "forced_mistake_avoidance",
          "forcedMistakeAvoidance",
        ])
      );

      return {
        driverName: bestDriverName(driver),
        carDesign: `${rand(0, 24)},${colors}`,
        carNumber: String(valueForKeys(driver, ["number", "carNumber", "car_number"]) || rand(0, 99)),
        suitDesign: `${rand(0, 24)},${colors}`,
        helmetDesign: `${rand(0, 24)},${colors}`,
        carPath: car?.FILEPATH || "",
        carId: intValue(car?.Iracing_ID),
        sponsor1: 0,
        sponsor2: 0,
        numberDesign: `${rand(0, 24)},${rand(0, 24)},${colors}`,
        driverSkill: skill,
        driverAggression: aggression,
        driverOptimism: avgPct(consistency, stamina),
        driverSmoothness: consistency,
        pitCrewSkill: avgPct(fuelManagement, tyreManagement),
        strategyRiskiness,
        driverAge: driverAge(driver),
        id: crypto.randomUUID(),
        rowIndex: index,
        carClassId: intValue(car?.Car_Class_ID),
      };
    }),
  };
}

function selectedChampionship() {
  const championshipId = championshipSelect.value;
  return state.championshipOptions.find((option) => option.championshipId === championshipId) || null;
}

function selectedCar(option) {
  const value = carSelect.value;
  if (!value || value === "__auto__") {
    return inferIracingCar(option);
  }
  return state.cars.find((car) => car.id === value) || inferIracingCar(option);
}

function inferIracingCar(option) {
  const hints = possibleCarHints(option.sourceDoc);
  if (!hints.length) {
    hints.push(option.label);
  }
  for (const hint of hints) {
    const normalized = hint.toLowerCase();
    const exact = state.cars.find((car) =>
      [car.Car, car["Car class"]].filter(Boolean).some((value) => value.toLowerCase() === normalized)
    );
    if (exact) return exact;
    const fuzzy = state.cars.find((car) =>
      [car.Car, car["Car class"]].filter(Boolean).some((value) => value.toLowerCase().includes(normalized))
    );
    if (fuzzy) return fuzzy;
  }
  return null;
}

function populateCarSelect() {
  carSelect.innerHTML = "";
  carSelect.append(new Option("Auto-detect", "__auto__"));
  for (const car of state.cars) {
    carSelect.append(new Option(carLabel(car), car.id));
  }
}

function selectCar(car) {
  carSelect.value = car?.id || "__auto__";
}

function carLabel(car) {
  return `${car["Car class"] || "Unknown"} | ${car.Car || "Unknown"}`;
}

async function loadIracingCars() {
  const response = await fetch(CARS_CSV_PATH);
  const text = await response.text();
  return parseCsv(text).filter((row) => String(row.Game || "").toLowerCase() === "iracing");
}

function parseCsv(text) {
  const rows = [];
  const lines = text.replace(/\r/g, "").split("\n").filter(Boolean);
  const headers = splitCsvLine(lines.shift());
  for (const line of lines) {
    const values = splitCsvLine(line);
    const row = {};
    headers.forEach((header, index) => {
      row[header] = values[index] || "";
    });
    rows.push(row);
  }
  return rows;
}

function splitCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (inQuotes && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      cells.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current);
  return cells;
}

function readDocsStore(dbName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName);
    request.onerror = () => reject(request.error || new Error(`Failed to open ${dbName}`));
    request.onsuccess = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("docs")) {
        db.close();
        resolve([]);
        return;
      }
      const tx = db.transaction("docs", "readonly");
      const store = tx.objectStore("docs");
      const getAllRequest = store.getAll();
      getAllRequest.onerror = () => reject(getAllRequest.error || new Error(`Failed to read docs from ${dbName}`));
      getAllRequest.onsuccess = () => {
        const docs = Array.isArray(getAllRequest.result) ? getAllRequest.result.filter((row) => row && typeof row === "object") : [];
        db.close();
        resolve(docs);
      };
    };
  });
}

function slotLabel(slotKey) {
  if (slotKey === "career-sim-main-db") return "Main DB";
  if (slotKey.startsWith("career-sim-slot-")) {
    return `Save Slot ${slotKey.replace("career-sim-slot-", "")}`;
  }
  return slotKey;
}

function bestDriverName(doc) {
  const firstName = firstNonEmptyString(
    nestedValueForKeys(doc, [
      "name",
      "first_name",
      "firstName",
      "given_name",
      "givenName",
      "forename",
      "name.first",
      "name.first_name",
      "name.firstName",
      "name.given",
      "name.given_name",
      "profile.first_name",
      "profile.firstName",
    ])
  );
  const lastName = firstNonEmptyString(
    nestedValueForKeys(doc, [
      "surname",
      "last_name",
      "lastName",
      "family_name",
      "familyName",
      "name.last",
      "name.last_name",
      "name.lastName",
      "name.family",
      "name.family_name",
      "profile.last_name",
      "profile.lastName",
    ])
  );
  const combined = `${firstName} ${lastName}`.trim();
  if (combined) return combined;

  const fullName = firstNonEmptyString(
    nestedValueForKeys(doc, [
      "full_name",
      "fullName",
      "display_name",
      "displayName",
      "driver_name",
      "driverName",
      "name.full",
      "name.full_name",
      "name.display",
      "profile.full_name",
      "profile.display_name",
    ])
  );
  if (fullName) return fullName;

  const nestedName = valueForKeys(doc, ["name"]);
  if (nestedName && typeof nestedName === "object") {
    const nestedFirst = firstNonEmptyString(
      nestedValueForKeys(nestedName, ["first", "first_name", "firstName", "given", "given_name", "forename"])
    );
    const nestedLast = firstNonEmptyString(
      nestedValueForKeys(nestedName, ["last", "last_name", "lastName", "surname", "family", "family_name"])
    );
    const nestedCombined = `${nestedFirst} ${nestedLast}`.trim();
    if (nestedCombined) return nestedCombined;
    const nestedFull = firstNonEmptyString(
      nestedValueForKeys(nestedName, ["full", "full_name", "display", "display_name", "value"])
    );
    if (nestedFull) return nestedFull;
  }

  const shortName = firstNonEmptyString(
    nestedValueForKeys(doc, ["name", "short_name", "shortName", "nickname"])
  );
  if (shortName) return shortName;

  return docId(doc) || "Unknown Driver";
}

function docLooksPlayer(doc) {
  if (!doc || typeof doc !== "object") return false;
  for (const [key, value] of Object.entries(doc)) {
    const normalized = normalizeKey(key);
    if (
      normalized === "isplayer" ||
      normalized === "player" ||
      normalized === "ishuman" ||
      normalized === "human" ||
      normalized === "playercontrolled" ||
      normalized === "controlledbyplayer" ||
      normalized === "iscontrolledbyplayer"
    ) {
      if (truthyLike(value)) return true;
    }
  }
  return false;
}

function looksPlayerRelated(doc, refs) {
  if (docLooksPlayer(doc)) return true;
  if (hasPlayerNameSignals(doc)) return true;
  if (docReferencesAny(doc, refs)) {
    for (const [key, value] of Object.entries(doc || {})) {
      const normalized = normalizeKey(key);
      if (
        normalized.includes("player") ||
        normalized.includes("human") ||
        normalized.includes("controlled")
      ) {
        if (truthyLike(value) || scalarStrings(value).length) {
          return true;
        }
      }
    }
  }
  return false;
}

function hasPlayerNameSignals(doc) {
  if (!doc || typeof doc !== "object") return false;
  return Boolean(
    bestPossiblePlayerName(doc) ||
    nestedValueForKeys(doc, [
      "player_name",
      "playerName",
      "player_full_name",
      "playerFullName",
      "player.name",
      "player.surname",
      "player.first_name",
      "player.last_name",
      "player.profile.name",
      "player.profile.surname",
    ])
  );
}

function playerDriverReferenceValues(doc) {
  const ids = new Set();
  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (
      normalized.includes("player") &&
      normalized.includes("driver")
    ) {
      for (const entry of scalarStrings(value)) {
        ids.add(entry);
      }
    }
  }
  if (!ids.size && docLooksPlayer(doc)) {
    for (const entry of driverReferenceValues(doc)) {
      ids.add(entry);
    }
  }
  return ids;
}

function playerNameCandidates(doc) {
  const names = new Set();
  const direct = bestPossiblePlayerName(doc);
  if (direct) names.add(normalizePersonName(direct));

  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (!normalized.includes("player")) continue;
    if (typeof value === "object" && value) {
      const nested = bestPossiblePlayerName(value);
      if (nested) names.add(normalizePersonName(nested));
    }
  }
  return new Set(Array.from(names).filter(Boolean));
}

function bestPossiblePlayerName(doc) {
  const fullName = firstNonEmptyString(
    nestedValueForKeys(doc, [
      "player_name",
      "playerName",
      "player_full_name",
      "playerFullName",
      "full_name",
      "fullName",
      "display_name",
      "displayName",
    ])
  );
  if (fullName) return fullName;

  const first = firstNonEmptyString(
    nestedValueForKeys(doc, ["name", "first_name", "firstName", "given_name", "givenName"])
  );
  const last = firstNonEmptyString(
    nestedValueForKeys(doc, ["surname", "last_name", "lastName", "family_name", "familyName"])
  );
  const combined = `${first} ${last}`.trim();
  return combined || "";
}

function bestChampionshipId(doc) {
  return String(valueForKeys(doc, ["championship_id", "championshipId", "id", "series_id", "seriesId"]) || "").trim();
}

function bestChampionshipLabel(doc) {
  for (const key of [
    "championship_name",
    "championshipName",
    "name",
    "display_name",
    "displayName",
    "series_name",
    "seriesName",
    "title",
  ]) {
    const value = valueForKeys(doc, [key]);
    if (value) return String(value).trim();
  }
  return bestChampionshipId(doc) || "Unknown Championship";
}

function docId(doc) {
  return String(valueForKeys(doc, ["id", "_id", "doc_id", "docId"]) || "").trim();
}

function championshipReferenceValues(doc) {
  const values = new Set();
  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (!normalized.includes("championship") || normalized.includes("entry")) {
      continue;
    }
    for (const entry of scalarStrings(value)) {
      values.add(entry);
    }
  }
  return values;
}

function possibleCarHints(doc) {
  const values = new Set();
  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (["car", "vehicle", "class"].some((token) => normalized.includes(token))) {
      for (const entry of scalarStrings(value)) {
        values.add(entry);
      }
    }
  }
  return Array.from(values);
}

function relationValues(doc) {
  const values = new Set();
  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (
      normalized.endsWith("id") ||
      normalized.endsWith("ids") ||
      normalized.includes("seat") ||
      normalized.includes("team") ||
      normalized.includes("championship")
    ) {
      for (const entry of scalarStrings(value)) {
        values.add(entry);
      }
    }
  }
  const selfId = docId(doc);
  if (selfId) values.add(selfId);
  return values;
}

function driverReferenceValues(doc) {
  const values = new Set();
  for (const [key, value] of Object.entries(doc || {})) {
    const normalized = normalizeKey(key);
    if (!normalized.includes("driver")) continue;
    if (
      DRIVER_ID_KEY_HINTS.some((hint) => normalized.includes(hint.replace(/_/g, ""))) ||
      normalized.endsWith("driver") ||
      normalized.endsWith("drivers")
    ) {
      for (const entry of scalarStrings(value)) {
        values.add(entry);
      }
    }
  }
  return values;
}

function truthyLike(value) {
  if (value === true || value === 1) return true;
  const text = String(value || "").trim().toLowerCase();
  return ["true", "yes", "player", "human"].includes(text);
}

function docReferencesAny(doc, refs) {
  const values = new Set([...relationValues(doc), ...driverReferenceValues(doc)]);
  return Array.from(values).some((value) => refs.has(value));
}

function valueForKeys(doc, keys) {
  if (!doc || typeof doc !== "object") return null;
  const normalized = new Map(
    Object.entries(doc).map(([key, value]) => [normalizeKey(key), value])
  );
  for (const key of keys) {
    const match = normalized.get(normalizeKey(key));
    if (match !== null && match !== undefined && match !== "") {
      return match;
    }
  }
  return null;
}

function nestedValueForKeys(doc, keys) {
  for (const key of keys) {
    const value = nestedValue(doc, key);
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return null;
}

function nestedValue(doc, path) {
  if (!doc || typeof doc !== "object") return null;
  const parts = String(path).split(".");
  let current = doc;
  for (const part of parts) {
    if (!current || typeof current !== "object") return null;
    const match = valueForKeys(current, [part]);
    if (match === null || match === undefined || match === "") {
      return null;
    }
    current = match;
  }
  return current;
}

function firstNonEmptyString(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const match = firstNonEmptyString(item);
      if (match) return match;
    }
    return "";
  }
  if (value && typeof value === "object") {
    return "";
  }
  return String(value || "").trim();
}

function scalarStrings(value) {
  if (value === null || value === undefined || value === "") return [];
  if (Array.isArray(value)) {
    return value.flatMap((entry) => scalarStrings(entry));
  }
  if (typeof value === "object") {
    return Object.values(value).flatMap((entry) => scalarStrings(entry));
  }
  return [String(value).trim()].filter(Boolean);
}

function normalizeKey(key) {
  return String(key).replace(/_/g, "").toLowerCase();
}

function normalizePersonName(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function denormalizePersonName(value) {
  return String(value || "")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function pctValue(value, fallback = 50) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  const scaled = number <= 1 ? number * 100 : number;
  return clamp(Math.round(scaled), 0, 100);
}

function avgPct(left, right) {
  return clamp(Math.round((left + right) / 2), 0, 100);
}

function intValue(value, fallback = 0) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) ? number : fallback;
}

function driverAge(doc) {
  const dob = valueForKeys(doc, [
    "dob",
    "date_of_birth",
    "dateOfBirth",
    "birth_date",
    "birthDate",
  ]);
  const calculated = ageFromDob(dob);
  if (calculated !== null) {
    return calculated;
  }
  return clamp(intValue(valueForKeys(doc, ["age", "driverAge", "driver_age"]), 28), 16, 80);
}

function ageFromDob(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const today = new Date();
  let age = today.getFullYear() - parsed.getFullYear();
  const monthDelta = today.getMonth() - parsed.getMonth();
  const dayDelta = today.getDate() - parsed.getDate();
  if (monthDelta < 0 || (monthDelta === 0 && dayDelta < 0)) {
    age -= 1;
  }
  return clamp(age, 16, 80);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function rand(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pick(values) {
  return values[rand(0, values.length - 1)];
}

function slugify(text) {
  return String(text).replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "") || "export";
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function setStatus(text, isError = false) {
  statusNode.textContent = text;
  statusNode.style.color = isError ? "#ff9f9f" : "";
}

function setSummary(text) {
  summaryNode.textContent = text;
}
