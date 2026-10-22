// static/dashboard.js
// Dynamically loads study statistics from REST API and renders Chart.js visualizations

document.addEventListener("DOMContentLoaded", function() {
    // Load statistics charts dynamically via REST API
    fetch('/api/v1/sessions')
        .then(response => {
            if (!response.ok) {
                throw new Error("Failed to fetch sessions data.");
            }
            return response.json();
        })
        .then(data => {
            if (!data || data.length === 0) return;

            // Sort chronologically
            data.sort((a, b) => new Date(a.session_date) - new Date(b.session_date));

            // 1. Line Chart Data
            const labels = data.map(s => {
                const d = new Date(s.session_date);
                return d.toLocaleDateString(undefined, {month: 'short', day: 'numeric'}) + ' ' + d.toLocaleTimeString(undefined, {hour: '2-digit', minute:'2-digit'});
            });
            const productivityScores = data.map(s => s.productivity_score);
            const studyHours = data.map(s => s.study_hours);

            // 2. Doughnut Chart Data (by subject)
            const subjectHours = {};
            data.forEach(s => {
                const list = s.subjects || [];
                if (list.length > 0) {
                    const alloc = parseFloat(s.study_hours) / list.length;
                    list.forEach(subj => {
                        const clean = subj.trim();
                        if (clean) {
                            subjectHours[clean] = (subjectHours[clean] || 0) + alloc;
                        }
                    });
                }
            });

            const subjectLabels = Object.keys(subjectHours);
            const subjectData = Object.values(subjectHours).map(h => Math.round(h * 10) / 10);

            // 3. Render Line Chart
            const ctxProd = document.getElementById('productivityChart').getContext('2d');
            new Chart(ctxProd, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Productivity Score',
                            data: productivityScores,
                            borderColor: '#3498db',
                            backgroundColor: 'rgba(52, 152, 219, 0.1)',
                            borderWidth: 2,
                            tension: 0.3,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Hours Studied',
                            data: studyHours,
                            borderColor: '#2ecc71',
                            backgroundColor: 'rgba(46, 204, 113, 0.1)',
                            borderWidth: 2,
                            tension: 0.3,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            min: 0,
                            max: 100,
                            title: {
                                display: true,
                                text: 'Productivity Score'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            min: 0,
                            grid: {
                                drawOnChartArea: false
                            },
                            title: {
                                display: true,
                                text: 'Hours Studied'
                            }
                        }
                    }
                }
            });

            // 4. Render Doughnut Chart
            const ctxSub = document.getElementById('subjectChart').getContext('2d');
            new Chart(ctxSub, {
                type: 'doughnut',
                data: {
                    labels: subjectLabels,
                    datasets: [{
                        data: subjectData,
                        backgroundColor: [
                            '#2ecc71', '#3498db', '#9b59b6', '#f1c40f',
                            '#e74c3c', '#1abc9c', '#e67e22', '#34495e'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 12,
                                padding: 10
                            }
                        }
                    }
                }
            });
        })
        .catch(err => {
            console.error("Dashboard error:", err);
        });
});
