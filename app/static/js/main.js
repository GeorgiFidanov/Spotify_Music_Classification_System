// Global variables
let spotifyClient = null;
let selectedCluster = null;
let treeData = null;
let userPlaylists = [];

// D3.js visualization setup
const width = document.getElementById('visualization').clientWidth;
const height = 600;
const margin = { top: 20, right: 90, bottom: 30, left: 90 };

// Initialize the visualization
function initVisualization() {
    const svg = d3.select('#visualization')
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.5, 2])
        .on('zoom', (event) => {
            svg.attr('transform', event.transform);
        });

    d3.select('#visualization svg').call(zoom);

    return svg;
}

// Create tree layout
function createTreeLayout(data) {
    const treeLayout = d3.tree()
        .size([height - margin.top - margin.bottom, width - margin.left - margin.right]);

    const root = d3.hierarchy(data);
    return treeLayout(root);
}

// Draw the tree
function drawTree(svg, treeData) {
    // Clear previous visualization
    svg.selectAll('*').remove();

    // Create links
    const link = svg.selectAll('.link')
        .data(treeData.links())
        .enter()
        .append('path')
        .attr('class', 'link')
        .attr('d', d3.linkHorizontal()
            .x(d => d.y)
            .y(d => d.x));

    // Create nodes
    const node = svg.selectAll('.node')
        .data(treeData.descendants())
        .enter()
        .append('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.y},${d.x})`);

    // Add circles to nodes
    node.append('circle')
        .attr('r', d => d.data.size || 5)
        .attr('fill', d => getClusterColor(d.data.cluster_id))
        .on('click', handleNodeClick);

    // Add labels to nodes
    node.append('text')
        .attr('dy', '.31em')
        .attr('x', d => d.children ? -6 : 6)
        .attr('text-anchor', d => d.children ? 'end' : 'start')
        .text(d => d.data.name)
        .clone(true)
        .lower()
        .attr('stroke', 'white')
        .attr('stroke-width', 3);

    // Add tooltips
    node.append('title')
        .text(d => {
            if (d.data.mood) {
                return `${d.data.name}\nMood: ${d.data.mood}\nSize: ${d.data.size} songs`;
            }
            return d.data.name;
        });
}

// Handle node click
function handleNodeClick(event, d) {
    selectedCluster = d.data;
    updateClusterInfo(d.data);
    document.getElementById('create-playlist').disabled = false;
}

// Update cluster information
function updateClusterInfo(cluster) {
    const infoDiv = document.getElementById('cluster-info');
    
    if (cluster.children) {
        // This is a cluster node
        infoDiv.innerHTML = `
            <div class="cluster-card">
                <h6>${cluster.name}</h6>
                <p>Size: ${cluster.size} songs</p>
                <p>Mood: ${cluster.mood}</p>
                <p>Avg Energy: ${(cluster.avg_energy * 100).toFixed(1)}%</p>
                <p>Avg Valence: ${(cluster.avg_valence * 100).toFixed(1)}%</p>
                <div class="track-list">
                    <h6>Top Tracks:</h6>
                    <ul>
                        ${cluster.children.slice(0, 5).map(track => `
                            <li>${track.name} - ${track.artist}</li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;
    } else {
        // This is a track node
        infoDiv.innerHTML = `
            <div class="cluster-card">
                <h6>${cluster.name}</h6>
                <p>Artist: ${cluster.artist}</p>
                <p>Popularity: ${cluster.popularity}%</p>
                <p>Energy: ${(cluster.energy * 100).toFixed(1)}%</p>
                <p>Valence: ${(cluster.valence * 100).toFixed(1)}%</p>
            </div>
        `;
    }
}

// Get color for cluster
function getClusterColor(clusterId) {
    const colors = [
        '#1DB954', // Spotify green
        '#1ED760', // Spotify light green
        '#1AA34A', // Dark green
        '#169C46', // Darker green
        '#0F7A35'  // Darkest green
    ];
    return colors[clusterId % colors.length];
}

// Initialize the application
async function init() {
    const loginButton = document.getElementById('login-button');
    if (loginButton) {
        loginButton.addEventListener('click', handleSpotifyLogin);
    }

    // Check if user is already logged in
    const token = localStorage.getItem('spotify_access_token');
    if (token) {
        await loadUserPlaylists();
    }

    // Add event listener for create playlist button
    const createPlaylistBtn = document.getElementById('create-playlist');
    if (createPlaylistBtn) {
        createPlaylistBtn.addEventListener('click', handleCreatePlaylist);
    }
}

// Handle Spotify login
async function handleSpotifyLogin() {
    try {
        const response = await fetch('/api/spotify/auth-url');
        const data = await response.json();
        window.location.href = data.auth_url;
    } catch (error) {
        console.error('Error getting auth URL:', error);
        alert('Error connecting to Spotify. Please try again.');
    }
}

// Fetch and display user playlists
async function loadUserPlaylists() {
    showLoading(true);
    try {
        const token = localStorage.getItem('spotify_access_token');
        const response = await fetch('/api/spotify/user-playlists', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        userPlaylists = data.items || [];
        renderPlaylistSelector(userPlaylists);
        showMainContent(true);
    } catch (error) {
        console.error('Error loading playlists:', error);
        alert('Error loading your playlists. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Render playlist selector UI
function renderPlaylistSelector(playlists) {
    const visDiv = document.getElementById('visualization');
    if (!visDiv) return;
    visDiv.innerHTML = `
        <div class="mb-4">
            <h5>Select a Playlist to Explore</h5>
            <select id="playlist-select" class="form-select mb-3">
                <option value="">-- Choose a playlist --</option>
                ${playlists.map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
            </select>
        </div>
        <div id="playlist-tracks"></div>
        <div id="cluster-results"></div>
    `;
    document.getElementById('playlist-select').addEventListener('change', handlePlaylistSelect);
}

// Handle playlist selection
async function handlePlaylistSelect(event) {
    const playlistId = event.target.value;
    if (!playlistId) return;
    await loadPlaylistTracks(playlistId);
}

// Fetch and display track names/IDs for selected playlist
async function loadPlaylistTracks(playlistId) {
    showLoading(true);
    try {
        const token = localStorage.getItem('spotify_access_token');
        const response = await fetch(`/api/spotify/playlist-tracks/${playlistId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        renderTrackList(data.items || [], playlistId);
    } catch (error) {
        console.error('Error loading playlist tracks:', error);
        alert('Error loading playlist tracks. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Render track list for selected playlist
function renderTrackList(tracks, playlistId) {
    const tracksDiv = document.getElementById('playlist-tracks');
    if (!tracksDiv) return;
    tracksDiv.innerHTML = `
        <h6>Tracks in Playlist</h6>
        <ul class="list-group mb-3">
            ${tracks.map(t => `<li class="list-group-item">${t.track.name} <span class="text-muted">(${t.track.id})</span></li>`).join('')}
        </ul>
        <button class="btn btn-primary" id="analyze-playlist">Analyze Playlist</button>
    `;
    document.getElementById('analyze-playlist').addEventListener('click', () => {
        analyzePlaylist(playlistId);
    });
}

// Analyze playlist and show clustering results
async function analyzePlaylist(playlistId) {
    showLoading(true);
    try {
        const token = localStorage.getItem('spotify_access_token');
        const response = await fetch(`/api/spotify/playlist-cluster/${playlistId}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        renderClusterResults(data);
    } catch (error) {
        console.error('Error analyzing playlist:', error);
        alert('Error analyzing playlist. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Render clustering results
function renderClusterResults(data) {
    const resultsDiv = document.getElementById('cluster-results');
    if (!resultsDiv) return;
    if (data && data.message) {
        resultsDiv.innerHTML = `<div class="alert alert-warning">${data.message}</div>`;
        return;
    }
    if (!data || !data.cluster_summaries || !data.cluster_labels || data.cluster_labels.length === 0) {
        resultsDiv.innerHTML = '<div class="alert alert-warning">No clustering results available.</div>';
        return;
    }
    resultsDiv.innerHTML = `
        <h6>Cluster Summaries</h6>
        <ul class="list-group mb-3">
            ${data.cluster_summaries.map(c => `
                <li class="list-group-item">
                    <strong>Cluster ${c.cluster_id + 1}:</strong> Size: ${c.size}, Mood: ${c.mood}, Avg Energy: ${(c.avg_energy * 100).toFixed(1)}%, Avg Valence: ${(c.avg_valence * 100).toFixed(1)}%
                </li>
            `).join('')}
        </ul>
    `;
}

// Handle create playlist
async function handleCreatePlaylist() {
    if (!selectedCluster || !selectedCluster.cluster_id) {
        alert('Please select a cluster first');
        return;
    }

    try {
        const token = localStorage.getItem('spotify_access_token');
        const response = await fetch('/api/playlist/create', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cluster_id: selectedCluster.cluster_id,
                name: `${selectedCluster.mood} Mix`,
                description: `A playlist of ${selectedCluster.mood} songs from your music collection`
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        alert('Playlist created successfully!');
    } catch (error) {
        console.error('Error creating playlist:', error);
        alert('Error creating playlist. Please try again.');
    }
}

// Show/hide loading spinner
function showLoading(show) {
    document.getElementById('loading').classList.toggle('d-none', !show);
}

// Show/hide main content
function showMainContent(show) {
    document.getElementById('main-content').classList.toggle('d-none', !show);
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', init); 