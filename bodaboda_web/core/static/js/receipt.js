const printButton = document.getElementById('receipt-print-btn');
if (printButton) {
  printButton.addEventListener('click', () => window.print());
}

const params = new URLSearchParams(window.location.search);
if (params.get('print') === '1') {
  setTimeout(() => window.print(), 300);
}
