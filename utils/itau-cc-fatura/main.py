import enum
from os import path, listdir, rename
import pandas as pd
import matplotlib.pyplot as plt
import pdftotext
import re

_VALID_CATEGORIES = ['VESTUÁRIO', 'DIVERSOS', 'ALIMENTAÇÃO', 'SAÚDE', 'VEÍCULOS', 'TURISMO', 'HOBBY', 'EDUCAÇÃO', 'MORADIA']

def get_pdf_text(pdf_file_name):
    with open(pdf_file_name, "rb") as f:
        pdf = pdftotext.PDF(f)

    pagina_abertura = 0
    pagina_fechamento = len(pdf) - 1

    return pdf, pagina_abertura, pagina_fechamento


def process_first_page(page):
    page_proc = page.split("\n")

    with open("first_page.txt", "w") as f:
        f.write(page)


    for line in page_proc:
        if line.find("Emissão") > 0:
            splitted_emissao = line.split("/")
            mes = splitted_emissao[1]
            ano = splitted_emissao[2]


        if line.strip()[:6] == "Cartão":
            text_linha_cartao = line.replace(" ", "")
            splitted_cartao = text_linha_cartao[6:].split('.')
            card_num = splitted_cartao[3][:4]
            card_name = splitted_cartao[3][4:]

    return mes, ano, card_num, card_name

def get_value(line):
    idx = line.rfind(" ") - 2

    value = float(line[idx:].strip().replace(".", "").replace(",", ".").replace(" ", ""))

    return value

def is_transaction_line(line):
    if re.findall("\d\d/\d\d", line[:5]) != []:
        return not line.find("ANUIDADE") > 0
    return False

def get_category(line):
    for category in _VALID_CATEGORIES:
        size = len(category)

        if(line[:size] == category):
            #print("Categoria: {}".format(category))
            return category

    return ""

def is_next_month(line):
    text_to_look = 'compras parceladas - próximas faturas'
    text_size = len(text_to_look)

    return text_to_look == line[:text_size].lower()

def process_transaction_page(page, i, ret_list = []):
    page_proc = page.split("\n")

    lista_1 = []
    lista_2 = []

    stop_add_2 = False
    ignore_list_2 = False

    for idx, line in enumerate(page_proc):
        if idx == 0:
            if len(line) < 70:
                return ret_list, True

            idx_second_col = line.rfind("Lançamentos")
        
        if idx_second_col < 40:
            idx_second_col = line.rfind("Compras")

        if idx_second_col < 40:
            idx_second_col = line.rfind("Pagamento")

        first_column = line[:idx_second_col].strip()
        last_column = line[idx_second_col:].strip()

        if is_next_month(first_column):
            ignore_list_2 = True
            break

        if (is_transaction_line(first_column) or get_category(first_column) != ""):
            lista_1.append(first_column)
        
        if is_next_month(last_column):
            stop_add_2 = True

        if ((not stop_add_2) and (is_transaction_line(last_column) or get_category(last_column) != "")): 
            lista_2.append(last_column)

    for transac in lista_1:
        ret_list.append(transac)
    
    if not ignore_list_2:
        for transac in lista_2:
            ret_list.append(transac)

    return ret_list, ignore_list_2 or stop_add_2

def processar_arquivo(filename):
    print("Processing: {}".format(filename))

    pdf, pg_0, pg_end = get_pdf_text(filename)
    rename(filename, "{}/{}".format("Processados", filename))
    #print("Total pages: {}".format(len(pdf)))
    transaction_list = []
    stop_processing = False

    # Processar PDF e extrair lista
    for idx, page in enumerate(pdf):
            if idx == pg_0:
                mes_emissao, ano_emissao, card_num, card_name = process_first_page(page)
            elif idx == pg_end:
                break
            else:
                if stop_processing:
                    continue

                transaction_list, stop_processing = process_transaction_page(page, idx, transaction_list)

            #print("indice: {}. Total de caracteres: {}".format(idx, len(page)))

    # Processar lista e gerar agrupamento por categoria

    i = 0
    listaFinal = []

    while i < len(transaction_list):
        if i+1 >= len(transaction_list):
            break

        valor = get_value(transaction_list[i])
        categoria = get_category(transaction_list[i+1])
        listaFinal.append(["{}/{}".format(ano_emissao, mes_emissao), categoria, valor])

        i += 2

    pd_csv = pd.DataFrame(listaFinal, columns=["AnoMes", "Categoria", "Valor"])
    pd_proc = pd_csv.groupby(['AnoMes', 'Categoria']).sum().reset_index()
    file_name = "{}_{}.csv".format(card_num, card_name)

    if path.isfile(file_name):
        pd_anterior = pd.read_csv(file_name)
        pd_final = pd.concat([pd_anterior, pd_proc])
    else:
        pd_final = pd_proc
    
    pd_final.sort_values(by=["AnoMes", "Categoria"], inplace=True)
    pd_final.to_csv(file_name, index=False)

    pd_pivot = pd_final.pivot(index="AnoMes", columns="Categoria")
    pd_pivot.to_csv(file_name.replace(".csv", "_proc.csv"))

if __name__ == '__main__':
    for file in listdir("."):
        if file[-3:] != "pdf":
            continue

        processar_arquivo(file)
