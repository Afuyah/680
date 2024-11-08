// Check if the browser supports service workers
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/service-worker.js') // Adjust the path if needed
            .then((registration) => {
                console.log('Service Worker registered with scope:', registration.scope);

                // Listen for updates to the Service Worker
                registration.onupdatefound = () => {
                    const installingWorker = registration.installing;

                    installingWorker.onstatechange = () => {
                        if (installingWorker.state === 'installed') {
                            if (navigator.serviceWorker.controller) {
                                // New content is available; ask user to refresh
                                console.log('New content is available; please refresh.');
                                if (confirm('New version available. Refresh?')) {
                                    // Reload the page to load the new version
                                    window.location.reload();
                                }
                            } else {
                                console.log('Content is cached for offline use.');
                            }
                        }
                    };
                };
            })
            .catch((error) => {
                console.error('Service Worker registration failed:', error);
            });
    });
}

// Function to manually refresh and get new content by updating Service Worker
function updateServiceWorker() {
    if (navigator.serviceWorker) {
        navigator.serviceWorker.getRegistration().then((registration) => {
            if (registration && registration.waiting) {
                registration.waiting.postMessage({ action: 'SKIP_WAITING' });
            }
        });
    }
}

// Example manual update trigger
const updateButton = document.getElementById('update-button');
if (updateButton) {
    updateButton.addEventListener('click', updateServiceWorker);
}
