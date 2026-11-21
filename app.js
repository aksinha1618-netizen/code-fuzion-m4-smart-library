// Smart Library Seat Finder - browser client for server.py
let currentFloor = 1;
let selectedSeat = null;
let myBooking = null;
let breakInterval = null;
let html5QrCode = null;
let lastError = "";

const userId = localStorage.getItem("slfUserId") || crypto.randomUUID();
localStorage.setItem("slfUserId", userId);
const seatGrid = document.getElementById("seatGrid");
const esc = encodeURIComponent;

async function api(path, data) {
  const response = await fetch(path, data ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  } : { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed. Try again.");
  return result;
}

function notifyError(error) {
  lastError = error.message || "Something went wrong.";
  alert(lastError);
}

async function refreshState() {
  try {
    const state = await api(`/api/state?floor=${currentFloor}&userId=${esc(userId)}`);
    myBooking = state.booking;
    document.getElementById("liveStatus").textContent = "● Live · updates automatically";
    renderSeats(state.seats);
    renderBooking();
    updateStatistics(state.seats);
  } catch (error) {
    document.getElementById("liveStatus").textContent = "● Reconnecting…";
    console.error(error);
  }
}

function renderSeats(seats) {
  if (selectedSeat && seats.some((seat) => seat.id === selectedSeat && seat.occupied)) {
    selectedSeat = null;
  }
  seatGrid.replaceChildren();
  seats.forEach((seat) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = seat.id;
    button.className = `seat ${seat.occupied ? "occupied" : selectedSeat === seat.id ? "selected" : "available"}`;
    button.disabled = seat.occupied;
    button.setAttribute("aria-label", `${seat.id}, ${seat.occupied ? "booked" : "available"}`);
    button.addEventListener("click", () => {
      if (myBooking) return alert("Cancel your current booking before selecting another seat.");
      selectedSeat = seat.id;
      document.getElementById("selectedSeat").textContent = selectedSeat;
      document.getElementById("bookButton").disabled = false;
      document.getElementById("showSeatQrButton").hidden = true;
      clearQr();
      renderSeats(seats);
    });
    seatGrid.append(button);
  });
}

function updateStatistics(seats) {
  const occupied = seats.filter((seat) => seat.occupied).length;
  document.getElementById("totalSeats").textContent = "450";
  document.getElementById("availableSeats").textContent = seats.length - occupied;
  document.getElementById("occupiedSeats").textContent = occupied;
}

function renderBooking() {
  const details = document.getElementById("bookingDetails");
  const cancel = document.getElementById("cancelButton");
  const bookButton = document.getElementById("bookButton");
  const showQr = document.getElementById("showSeatQrButton");
  const scanButton = document.getElementById("startScannerButton");
  bookButton.disabled = !selectedSeat || !!myBooking;
  document.getElementById("selectedSeat").textContent = selectedSeat || "None";

  if (!myBooking) {
    details.innerHTML = "<p>You haven't booked a seat yet.</p>";
    cancel.hidden = true;
    showQr.hidden = true;
    scanButton.disabled = true;
    document.getElementById("checkinStatus").textContent = "Book a seat first. Scan the QR label placed at that seat.";
    return;
  }

  const status = myBooking.checked_in ? "Checked in" : "Booked · awaiting check-in";
  const breakLine = myBooking.on_break ? " · 20-minute break in progress" : "";
  details.replaceChildren();
  const heading = document.createElement("h3"); heading.textContent = "Booking confirmed";
  const seatLine = document.createElement("p"); seatLine.textContent = `Seat: ${myBooking.seat_id}`;
  const floorLine = document.createElement("p"); floorLine.textContent = `Floor: ${myBooking.seat_id.split("-")[0].slice(1)}`;
  const statusLine = document.createElement("p"); statusLine.textContent = `Status: ${status}${breakLine}`;
  details.append(heading, seatLine, floorLine, statusLine);

  if (myBooking.checked_in && !myBooking.on_break) {
    const breakButton = document.createElement("button");
    breakButton.textContent = "Start 20-minute break";
    breakButton.addEventListener("click", startBreak);
    details.append(breakButton);
  }
  if (myBooking.on_break) {
    const timerHeading = document.createElement("h3"); timerHeading.textContent = "Break timer";
    const timer = document.createElement("p"); timer.id = "breakCountdown"; timer.className = "break-countdown";
    details.append(timerHeading, timer);
    startBreakCountdown();
  } else if (breakInterval) {
    clearInterval(breakInterval); breakInterval = null;
  }

  cancel.hidden = false;
  showQr.hidden = false;
  scanButton.disabled = !!myBooking.checked_in;
  document.getElementById("checkinStatus").textContent = myBooking.checked_in
    ? "Check-in completed. Start a break when you leave your seat."
    : "Scan the fixed QR label at your seat to check in.";
}

function clearQr() {
  document.getElementById("qrCode").replaceChildren();
}

function displaySeatQr() {
  if (!myBooking || typeof QRCode === "undefined") {
    return alert("QR code library did not load. Check your internet connection and refresh.");
  }
  clearQr();
  new QRCode(document.getElementById("qrCode"), {
    text: `SLF|SEAT|${myBooking.seat_id}`, width: 180, height: 180
  });
  document.getElementById("checkinStatus").textContent = `Demo QR for ${myBooking.seat_id}. In the library, a fixed printed QR would be placed at this seat.`;
}

async function startBreak() {
  try { await api("/api/break", { userId }); await refreshState(); }
  catch (error) { notifyError(error); }
}

function startBreakCountdown() {
  if (breakInterval) return;
  breakInterval = setInterval(() => {
    if (!myBooking || !myBooking.on_break) {
      clearInterval(breakInterval); breakInterval = null; return;
    }
    const remaining = Math.max(0, myBooking.break_ends_at * 1000 - Date.now());
    const node = document.getElementById("breakCountdown");
    if (node) node.textContent = `${String(Math.floor(remaining / 60000)).padStart(2, "0")}:${String(Math.floor((remaining % 60000) / 1000)).padStart(2, "0")}`;
    if (remaining === 0) refreshState();
  }, 1000);
}

document.querySelectorAll(".floor-btn").forEach((button) => {
  button.addEventListener("click", () => {
    currentFloor = Number(button.dataset.floor);
    document.querySelectorAll(".floor-btn").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    selectedSeat = null;
    document.getElementById("selectedSeat").textContent = "None";
    document.getElementById("bookButton").disabled = true;
    document.getElementById("showSeatQrButton").hidden = true;
    clearQr();
    refreshState();
  });
});

document.getElementById("bookButton").addEventListener("click", async () => {
  if (!selectedSeat || myBooking) return;
  try {
    await api("/api/book", { userId, seatId: selectedSeat });
    selectedSeat = null;
    document.getElementById("selectedSeat").textContent = "None";
    clearQr();
    await refreshState();
    await loadAdminStats();
  } catch (error) { notifyError(error); await refreshState(); }
});

document.getElementById("cancelButton").addEventListener("click", async () => {
  try {
    await api("/api/cancel", { userId });
    myBooking = null; selectedSeat = null; clearQr(); await refreshState(); await loadAdminStats();
  } catch (error) { notifyError(error); }
});

document.getElementById("showSeatQrButton").addEventListener("click", displaySeatQr);

document.getElementById("startScannerButton").addEventListener("click", async () => {
  if (!myBooking || myBooking.checked_in) return;
  if (typeof Html5Qrcode === "undefined") return alert("Scanner library did not load. Check your internet connection.");
  try {
    html5QrCode = new Html5Qrcode("reader");
    await html5QrCode.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 220, height: 220 } }, async (decodedText) => {
      if (decodedText !== `SLF|SEAT|${myBooking.seat_id}`) {
        document.getElementById("checkinStatus").textContent = "That QR is for a different seat.";
        return;
      }
      try {
        await api("/api/checkin", { userId, seatId: myBooking.seat_id });
        await html5QrCode.stop(); html5QrCode = null;
        clearQr(); await refreshState(); await loadAdminStats();
        document.getElementById("checkinStatus").textContent = "Check-in successful!";
      } catch (error) { notifyError(error); }
    });
  } catch (error) {
    alert("Camera could not start. Use HTTPS (or localhost) and allow camera access.");
    console.error(error);
  }
});

async function loadAdminStats() {
  try {
    const stats = await api("/api/admin/stats");
    document.getElementById("adminActive").textContent = stats.activeBookings;
    document.getElementById("adminHistory").textContent = stats.bookingHistory;
    fillList("peakHours", stats.peakHours.map((item) => `${item.hour}:00–${item.hour}:59 IST · ${item.bookings} booking(s)`), "No bookings yet.");
    fillList("hoggedSeats", stats.mostBookedSeats.map((item) => `${item.seat_id} · ${item.bookings} booking(s)`), "No bookings yet.");
  } catch (error) { console.error(error); }
}

function fillList(id, entries, emptyText) {
  const list = document.getElementById(id); list.replaceChildren();
  (entries.length ? entries : [emptyText]).forEach((entry) => {
    const item = document.createElement("li"); item.textContent = entry; list.append(item);
  });
}

const events = new EventSource("/api/events");
events.onmessage = () => { refreshState(); loadAdminStats(); };
events.onerror = () => { document.getElementById("liveStatus").textContent = "● Reconnecting…"; };

refreshState();
loadAdminStats();
