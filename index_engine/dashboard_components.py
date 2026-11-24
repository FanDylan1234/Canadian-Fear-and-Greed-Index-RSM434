from dash import html


def table(headers, rows, numeric_columns=()):
    return html.Div(
        html.Table([
            html.Thead(html.Tr([html.Th(h, scope="col", className="numeric" if i in numeric_columns else "")
                                for i, h in enumerate(headers)])),
            html.Tbody([html.Tr([html.Td(cell, className="numeric" if i in numeric_columns else "")
                                 for i, cell in enumerate(row)]) for row in rows]),
        ]),
        className="table-scroll",
    )
