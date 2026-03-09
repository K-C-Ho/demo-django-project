// Room search
document.getElementById('roomSearch').addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase();
    document.querySelectorAll('.room-item').forEach(item => {
        const name = item.querySelector('h6').textContent.toLowerCase();
        item.style.display = name.includes(query) ? '' : 'none';
    });
});