function GetShoppingCart() {
    const shoppingCart = JSON.parse(sessionStorage.getItem("shoppingCart") || "[]");
    if (!Array.isArray(shoppingCart)) {
        console.error("Invalid shopping cart data:", shoppingCart);
        return [];
    }
    return shoppingCart;
}

function CleanShoppingCart() {
    const shoppingCart = GetShoppingCart().filter(Boolean);
    sessionStorage.setItem("shoppingCart", JSON.stringify(shoppingCart));
    return shoppingCart;
}

function SetInCartText() {
    const shoppingCart = GetShoppingCart().filter(Boolean);
    const numItems = shoppingCart.length;
    const inCartItems = document.getElementById("inCartItems");
    if (numItems > 0) {
        Sugar.Number.setOption('thousands', ' ');
        const totalPrice = Sugar.Number(shoppingCart.reduce((total, item) => total + (item.price || 0) * (item.quantity || 0), 0));
        inCartItems.textContent = `${numItems} позиции на сумму ${totalPrice.format(2)}`;
    } else {
        inCartItems.textContent = "";
    }
}

function PopulateSelectClones(form, itemPos = null) {

    const productId = Number(form.dataset.id);
    const selectClones = form.querySelector(".selectClones");
    const content = document.createDocumentFragment();
    const shoppingCart = CleanShoppingCart();
    selectClones.innerHTML = "";
    const addNewOpt = document.createElement('option');
    addNewOpt.classList.add('text-primary');
    addNewOpt.textContent = 'Добавить новый вариант';
    if (itemPos === null)
        addNewOpt.setAttribute("selected", "true");
    selectClones.appendChild(addNewOpt);
    let count = 0;
    shoppingCart.forEach((item, index) => {
        if (item.id === productId) {
            const opt = CreateSelectCloneOption(item, index);
            if (index === itemPos || (count === 0 && itemPos === -1)) {
                opt.setAttribute("selected", "true");
                itemPos = index;
            }
            content.appendChild(opt);
            count++;
        }
    });
    if (count === 0) {
        selectClones.closest(".row").classList.add("d-none");
        itemPos = null;
    } else {
        selectClones.closest(".row").classList.remove("d-none");
        selectClones.appendChild(content);
    }
    return itemPos
}

function PopulateCartProducts() {
    let shoppingCart = CleanShoppingCart();
    shoppingCart.forEach(PopulateProduct);
    const submitButton = document.querySelector("#submit");
    const comment = document.querySelector("#comment");
    const emptyCartAlert = document.querySelector("#emptyCartAlert");
    if (shoppingCart.length > 0) {
        submitButton.classList.remove("d-none");
        comment.classList.remove("d-none");
        emptyCartAlert.classList.add("d-none");
    }
    submitButton.addEventListener("click", function () {
        shoppingCart = [];
        sessionStorage.setItem('shoppingCart', JSON.stringify(shoppingCart));
    });
    SetInCartText();
}

function PopulateProductQuantities() {
    const cartItems = CleanShoppingCart();
    for (const item of cartItems) {
        const input = document.querySelector(`#product${item.id} input`);
        const plusSign = document.querySelector(`#product${item.id} input+span`);

        if (input) {
            const prevValue = Number(input.value);
            input.value = prevValue + item.quantity;
            input.classList.add("border-success");
            plusSign.classList.remove("d-none");
        }
    }
}

function PopulateProduct(item, index) {
    if (!item) {
        return;
    }
    const content = document.querySelector("#cartItemTemplate").cloneNode(true);
    const sku = content.querySelector("#productSkuTemplate");
    const name = content.querySelector("#productNameTemplate");
    const text = content.querySelector("#productTextTemplate");
    const image = content.querySelector("#productImageTemplate");
    const vendor = content.querySelector("#productVendorTemplate");
    const price = content.querySelector("#productPriceTemplate");
    const product = content.querySelector("#productIdTemplate");
    const quantity = content.querySelector("#productQuantityTemplate");
    const measurement = content.querySelector("#productMeasurementTemplate");
    const options = content.querySelector("#productOptionsTemplate");
    const optionsValues = content.querySelector("#productOptionsValuesTemplate");
    const textValue = content.querySelector("#productTextValueTemplate");
    const cloneProductButton = content.querySelector(".cloneProductButton");

    content.removeAttribute("id");
    sku.removeAttribute("id");
    name.removeAttribute("id");
    text.removeAttribute("id");
    image.removeAttribute("id");
    vendor.removeAttribute("id");
    price.removeAttribute("id");
    product.removeAttribute("id");
    quantity.removeAttribute("id");
    measurement.removeAttribute("id");
    options.removeAttribute("id");
    optionsValues.removeAttribute("id");
    textValue.removeAttribute("id");

    content.dataset.id = item.id;
    content.dataset.pos = index;
    content.dataset.cost = Number(item.price) * Number(item.quantity);

    sku.textContent = item.sku;
    name.textContent = item.name;
    if (item.text) {
        text.value = item.text;
        textValue.textContent = item.text;
        let parentRow = textValue.parentNode;
        while (parentRow && !parentRow.classList.contains("row")) {
            parentRow = parentRow.parentNode;
        }
        if (parentRow) {
            parentRow.classList.remove("d-none");
        }
    }
    if (item.image) {
        image.setAttribute("src", item.image);
    }
    vendor.textContent = item.vendor;
    price.textContent = item.price.toFixed(2);
    product.value = item.id;
    quantity.value = item.quantity;
    measurement.textContent = item.measurement;
    if (item.options) {
        options.value = JSON.stringify(item.options);
        const optionsKeys = Object.keys(item.options);
        const optionsValuesArr = optionsKeys.map(key => `${key}: <strong>${item.options[key]}</strong>`);
        optionsValues.innerHTML = optionsValuesArr.join(", ");
        optionsValues.closest(".row").classList.remove("d-none")
    }
    text.setAttribute("name", text.getAttribute("name").replace("_", index));
    product.setAttribute("name", product.getAttribute("name").replace("_", index));
    quantity.setAttribute("name", quantity.getAttribute("name").replace("_", index));
    options.setAttribute("name", options.getAttribute("name").replace("_", index));

    cloneProductButton.addEventListener('click', HandleCloneProduct);
    content.addEventListener('click', ShowCartModal);

    document.querySelector("#shoppingCartItems").appendChild(content);
}

function productOptionsToJson(form) {
    let formData = {};
    let selectElements = form.querySelectorAll("select.productOption");
    const numElements = selectElements.length;
    for (let i = 0; i < numElements; i++) {
        let selected = selectElements[i].querySelector("option:checked");
        let name = selectElements[i].name;
        if (!selected.disabled) {
            formData[name] = selected.value;
        }
    }
    return formData;
}

function AddToCart(form, itemPos = null) {

    const shoppingCart = CleanShoppingCart();
    const productId = Number(form.dataset.id);
    const quantityInput = form.querySelector(".productQuantity");
    const itemQuantity = Number(quantityInput.value);
    const itemText = form.querySelector(".productText").value;
    const itemOptions = productOptionsToJson(form);

    if (itemQuantity > 0) {
        let item = {};
        if (Number.isInteger(itemPos))
            item = shoppingCart[itemPos];
        else {
            item = {
                id: productId,
                name: form.dataset.name,
                sku: form.dataset.sku,
                price: Number(form.dataset.price),
                vendor: form.dataset.vendor,
                image: form.dataset.image,
                measurement: form.dataset.measurement
            };
            itemPos = shoppingCart.push(item) - 1;
        }

        if (itemText) {
            item.text = itemText;
        }
        if (itemOptions) {
            item.options = itemOptions;
        }
        item.quantity = itemQuantity;
    } else {
        if (Number.isInteger(itemPos))
            shoppingCart.splice(itemPos, 1);
        itemPos = null;
    }

    const productQuantityInput = document.querySelector(`#product${productId} input`);
    const totalQuantity = shoppingCart.reduce(function (acc, i) {
        if (i.id == productId)
            acc += i.quantity;
        return acc;
    }, 0);
    const plusSign = document.querySelector(`#product${productId} input+span`);
    if (totalQuantity > 0) {
        productQuantityInput.value = totalQuantity;
        productQuantityInput.classList.add("border-success");
        plusSign.classList.remove("d-none");
    } else {
        productQuantityInput.value = "";
        productQuantityInput.classList.remove("border-success");
        plusSign.classList.add("d-none");
    }
    sessionStorage.setItem("shoppingCart", JSON.stringify(shoppingCart));
    SyncProductModal(form, itemPos)
    SetInCartText();
}


function SyncProductModal(form, itemPos) {

    const addToCartButton = form.querySelector(".addToCart");
    const quantityInput = form.querySelector(".productQuantity");
    const textInput = form.querySelector(".productText");
    itemPos = PopulateSelectClones(form, itemPos);
    const productOptions = form.querySelectorAll(".productOption");
    if (!Number.isInteger(itemPos)) {
        addToCartButton.removeAttribute("data-pos");
        quantityInput.value = "";
        textInput.value = "";
        productOptions.forEach((select) => { select.value = 0 });
    }
    else {
        const shoppingCart = CleanShoppingCart();
        const item = shoppingCart[itemPos];
        addToCartButton.dataset.pos = itemPos;
        quantityInput.value = item.quantity;
        textInput.value = item.text || "";
        productOptions.forEach((select) => {
            const name = select.name;
            if (name in item.options)
                select.value = item.options[name];
            else
                select.value = 0;
            select.dispatchEvent(new Event("change"));
        });
    }
    quantityInput.focus();
}

function SyncCartModal(form, itemPos) {

    const shoppingCart = GetShoppingCart();
    const item = shoppingCart[itemPos];
    if (!item)
        return;

    form.dataset.pos = itemPos;
    const descriptionModalLabel = document.getElementById("descriptionModalLabel");
    descriptionModalLabel.textContent = item.name;

    const descriptionModalProductMeasurement = document.getElementById("descriptionModalProductMeasurement");
    descriptionModalProductMeasurement.textContent = item.measurement;

    const quantityInput = document.getElementById("descriptionModalProductQuantity");
    quantityInput.value = item.quantity;
    quantityInput.focus();

    const textInput = document.getElementById("descriptionModalProductText");
    textInput.value = item.text || "";

    const descriptionModalProductOptions = document.getElementById("descriptionModalProductOptions");
    descriptionModalProductOptions.innerHTML = "";
    let content = document.createDocumentFragment();
    const optionsKeys = Object.keys(item.options);
    optionsKeys.forEach((key) => {
        const row = document.createElement("div");
        row.classList.add("mb-3");
        const label = document.createElement("label");
        label.classList.add("form-label");
        label.textContent = key;
        const input = document.createElement("input");
        input.classList.add("form-control");
        input.value = item.options[key];
        input.setAttribute("readonly", "true");
        input.setAttribute("disabled", "true");
        input.setAttribute("type", "text");
        row.appendChild(label);
        row.appendChild(input);
        content.appendChild(row);
    });
    descriptionModalProductOptions.appendChild(content);

    const image = form.querySelector("img");
    if (item.image)
        image.setAttribute("src", item.image);
    else
        image.setAttribute("src", "");
}

function CreateSelectCloneOption(item, index) {
    const opt = document.createElement("option");
    opt.value = index;
    opt.textContent = `${item.quantity} ${item.measurement}`;
    if (item.options) {
        const optionsKeys = Object.keys(item.options);
        if (optionsKeys.length > 0) {
            const optionsValuesArr = optionsKeys.map(key => `${key}: ${item.options[key]}`);
            opt.textContent += ", " + optionsValuesArr.join(", ");
        }
    }
    if (item.text)
        opt.textContent += `, ${item.text}`;
    return opt;
}

function HandleProductModalChangeClone(event) {
    event.preventDefault();

    const currentClone = event.currentTarget;
    const itemPos = Number(currentClone.value);

    const modal = currentClone.closest(".modal");
    SyncProductModal(modal, itemPos);
}

function HandleCloneProduct(event) {
    event.preventDefault();
    event.stopPropagation();
    const shoppingCart = GetShoppingCart();
    const content = event.target.closest('.cartItem');
    const productPos = Number(content.dataset.pos);
    let item = shoppingCart[productPos];
    if (item) {
        shoppingCart.push(item);
        sessionStorage.setItem("shoppingCart", JSON.stringify(shoppingCart));
        PopulateProduct(item, shoppingCart.length - 1);
        SetInCartText();
    }
}

function HandleAddToCart(event) {
    const button = event.currentTarget;
    const itemPos = Number(button.dataset.pos);
    const modal = button.closest(".modal");
    AddToCart(modal, itemPos);
}

function HandleAddToCart2(event) {

    let shoppingCart = GetShoppingCart();
    const form = event.target.closest('.modal');
    const productPos = Number(form.dataset.pos);
    const quantityInput = document.getElementById("descriptionModalProductQuantity");
    const textInput = document.getElementById("descriptionModalProductText");
    const itemQuantity = Number(quantityInput.value);
    const itemText = textInput.value;
    let cartItem = document.querySelector(`div.cartItem[data-pos="${productPos}"]`);

    if (!itemQuantity || itemQuantity == 0) {
        shoppingCart[productPos] = null;
        cartItem.remove();
    } else {
        shoppingCart[productPos]['quantity'] = itemQuantity;
        shoppingCart[productPos]['text'] = itemText;
        let quantityInput = cartItem.querySelector(".productQuantity");
        quantityInput.value = itemQuantity;
        let textInput = cartItem.querySelector(".productTextValue");
        textInput.textContent = itemText;
        if (itemText) {
            textInput.closest('.row').classList.remove('d-none');
        }
        else {
            textInput.closest('.row').classList.add('d-none');
        }
    }

    if (shoppingCart.filter(Boolean).length == 0) {
        shoppingCart = [];
        const submitButton = document.querySelector("#submit");
        const comment = document.querySelector("#comment");
        const emptyCartAlert = document.querySelector("#emptyCartAlert");
        submitButton.classList.add("d-none");
        emptyCartAlert.classList.remove("d-none");
        comment.classList.add("d-none");
    }
    sessionStorage.setItem('shoppingCart', JSON.stringify(shoppingCart));
    SetInCartText(shoppingCart);
}

function ShowProductModal(event) {
    const productId = Number(event.currentTarget.dataset.id);
    const modalElement = document.getElementById(`descriptionModal${productId}`);
    let descriptionModal = bootstrap.Modal.getInstance(modalElement);
    if (!descriptionModal) {
        descriptionModal = new bootstrap.Modal(modalElement, {});
    }
    SyncProductModal(modalElement, -1);
    descriptionModal.show();
}

function ShowCartModal(event) {
    const itemPos = Number(event.currentTarget.dataset.pos);
    const modalElement = document.getElementById("descriptionModal");
    let descriptionModal = bootstrap.Modal.getInstance(modalElement);
    if (!descriptionModal)
        descriptionModal = new bootstrap.Modal(modalElement, {});
    SyncCartModal(modalElement, itemPos);
    descriptionModal.show();
}

function CheckProject(selectProjectCallback) {


    const projectId = Number(
        document.cookie
            .split("; ")
            .find((row) => row.startsWith("project_id="))
            ?.split("=")[1]
    );

    const projectName = document.cookie
        .split("; ")
        .find((row) => row.startsWith("project_name="))
        ?.split("=")[1];

    const projectSelect = document.querySelector(".projectSelect");
    if (!projectId || !projectName)
        selectProjectCallback();
    else {
        document.querySelector("#projectName").textContent = projectName;
    }
    projectSelect.addEventListener("click", function () {
        document.cookie = "project_id=;";
        document.cookie = "project_name=;";
        selectProjectCallback();
    });
    return [projectId, projectName];
}
