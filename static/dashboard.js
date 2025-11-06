document.addEventListener("DOMContentLoaded", () => {
    const addBtn = document.getElementById("add-btn");
    const expenseList = document.getElementById("expense-list");

    // Add Expense
    addBtn.addEventListener("click", async () => {
        const title = document.getElementById("title").value.trim();
        const amount = document.getElementById("amount").value.trim();
        const category = document.getElementById("category").value.trim();

        if (!title || !amount || !category) return alert("Fill all fields!");

        const formData = new FormData();
        formData.append("title", title);
        formData.append("amount", amount);
        formData.append("category", category);

        const res = await fetch("/add", { method: "POST", body: formData });
        const data = await res.json();

        if (data.status === "success") {
            appendExpense(data.data);
            document.getElementById("title").value = "";
            document.getElementById("amount").value = "";
            document.getElementById("category").value = "";
            updateChart();
        }
    });

    // Delete Expense
    expenseList.addEventListener("click", async (e) => {
        if (e.target.classList.contains("delete-btn")) {
            const id = e.target.dataset.id;
            await fetch(`/delete/${id}`, { method: "DELETE" });
            e.target.parentElement.remove();
            updateChart();
        }
    });

    // Append new expense
    function appendExpense(exp) {
        const li = document.createElement("li");
        li.innerHTML = `
            <span>${exp.title}</span>
            <span>₹${exp.amount}</span>
            <span>${exp.category}</span>
            <span>${exp.date}</span>
            <button class="delete-btn" data-id="${exp.id}">✖</button>
        `;
        expenseList.appendChild(li);
    }

    // Chart.js
    const ctx = document.getElementById("chart");
    let chart;

    async function updateChart() {
        const res = await fetch("/api/data");
        const data = await res.json();

        const categories = {};
        data.forEach(d => {
            categories[d.category] = (categories[d.category] || 0) + d.amount;
        });

        const labels = Object.keys(categories);
        const values = Object.values(categories);

        if (chart) chart.destroy();

        chart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    label: "Expenses by Category",
                    data: values,
                    backgroundColor: [
                        "#00ffff88", "#7f00ff88", "#ff00c888", "#00e0ff88", "#f7258588"
                    ],
                    borderColor: "transparent"
                }]
            },
            options: {
                plugins: { legend: { labels: { color: "white" } } },
            }
        });
    }

    updateChart();
    setInterval(updateChart, 5000);
});
