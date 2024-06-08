function InstantiatePagination(itemsWrapperId, itemClass, paginationId, itemsPerPage, itemsFilterId) {
    const pagination = document.getElementById(paginationId);
    const itemsWrapper = document.getElementById(itemsWrapperId);
    const items = itemsWrapper.querySelectorAll(`.${itemClass}`);
    const pageCount = Math.ceil(items.length / itemsPerPage);
    const itemsFilter = document.getElementById(itemsFilterId);
    pagination.innerHTML = "";

    const setCurrentPage = (pageNum) => {
        if (itemsFilter)
            itemsFilter.value = "";
        const prevRange = (pageNum - 1) * itemsPerPage;
        const currRange = pageNum * itemsPerPage;
        const pageLinks = pagination.querySelectorAll("li.page-item");
        pageLinks.forEach((link) => { link.classList.remove("active") });
        const currentLink = pagination.querySelector(`li.page-item[data-page="${pageNum}"]`);
        if (currentLink) {
            currentLink.classList.add("active");
        }
        items.forEach((item, index) => {
            const showItem = (index >= prevRange && index < currRange);
            if (showItem)
                item.classList.remove("d-none")
            else
                item.classList.add("d-none");
        });
    }

    const appendPageNumber = (index, content) => {
        const li = document.createElement("li");
        li.className = "page-item";
        li.dataset.page = index;
        const a = document.createElement("a");
        a.textContent = index;
        a.className = "page-link";
        a.href = "#";
        li.addEventListener("click", () => {
            setCurrentPage(index);
        });
        li.appendChild(a);
        content.appendChild(li);
    };

    const getPaginationNumbers = (pageCount) => {
        const content = document.createDocumentFragment();
        for (let i = 1; i <= pageCount; i++) {
            appendPageNumber(i, content);
        }
        return content;
    };

    pagination.appendChild(getPaginationNumbers(pageCount));
    setCurrentPage(1);
}

