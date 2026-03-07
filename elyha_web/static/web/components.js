(function () {
  "use strict";

  const h = React.createElement;
  const { useEffect, useState } = React;

  function MetaItem(props) {
    return h(
      "div",
      { className: "meta-item" },
      h("strong", null, props.label),
      h("span", null, props.value)
    );
  }

  function Modal(props) {
    const modal = props.modal;
    const [inputValue, setInputValue] = useState("");

    useEffect(
      function () {
        if (!modal) {
          setInputValue("");
          return;
        }
        setInputValue(modal.defaultValue || "");
      },
      [modal ? modal.id : ""]
    );

    if (!modal) {
      return null;
    }

    function onSubmit() {
      if (modal.mode === "input") {
        props.onResolve({ confirmed: true, value: inputValue });
        return;
      }
      props.onResolve({ confirmed: true });
    }

    return h(
      "div",
      { className: "modal-root", role: "presentation" },
      h(
        "div",
        {
          className: "modal-card",
          role: "dialog",
          "aria-modal": "true",
          "aria-labelledby": "elyha-modal-title"
        },
        h("h3", { id: "elyha-modal-title" }, modal.title),
        h(
          "div",
          { className: "modal-body" },
          h("p", { className: "modal-copy" }, modal.body),
          modal.mode === "input"
            ? h("input", {
                className: "modal-input",
                value: inputValue,
                placeholder: modal.placeholder || "",
                onChange: function (event) {
                  setInputValue(event.target.value);
                },
                onKeyDown: function (event) {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onSubmit();
                  }
                },
                autoFocus: true
              })
            : null
        ),
        h(
          "div",
          { className: "modal-actions" },
          h(
            "button",
            {
              className: "btn ghost",
              onClick: function () {
                props.onResolve({ confirmed: false });
              }
            },
            modal.cancelText
          ),
          h(
            "button",
            {
              className: "btn",
              onClick: onSubmit
            },
            modal.confirmText
          )
        )
      )
    );
  }

  window.ElyhaWebComponents = {
    MetaItem: MetaItem,
    Modal: Modal
  };
})();
