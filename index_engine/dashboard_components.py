from dash import html


def table(headers, rows):
    return html.Div(
        html.Table([
            html.Thead(html.Tr([html.Th(h, scope="col") for h in headers])),
            html.Tbody([html.Tr([html.Td(cell) for cell in row]) for row in rows]),
        ]),
        className="table-scroll",
    )
