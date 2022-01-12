from os import path, listdir, rename
import pandas as pd
import pdftotext
import re

_VALID_CATEGORIES = ['VESTUÁRIO', 'DIVERSOS', 'ALIMENTAÇÃO', 'SAÚDE', 'VEÍCULOS', 'TURISMO', 'HOBBY', 'EDUCAÇÃO', 'MORADIA']

def pdf_to_text(arquivo_pdf):
    '''
    Opens the pdf, converts to text and returns it.
    Also returns the number of the last page
    '''
    with open(arquivo_pdf, "rb") as f:
        pdf = pdftotext.PDF(f)

    last_page_num = len(pdf) - 1

    return pdf, last_page_num


def process_first_page(page):
    '''
    The first page contains general info. Here the fucntion will extract the card informations
    Returns: The invoice month and year, card number and card name
    '''
    page_proc = page.split("\n")

    for line in page_proc:
        # Invoice information
        if line.find("Emissão") > 0:
            splitted_emissao = line.split("/")
            mes = splitted_emissao[1]
            ano = splitted_emissao[2]

        # Card information
        if line.strip()[:6] == "Cartão":
            text_linha_cartao = line.replace(" ", "")
            splitted_cartao = text_linha_cartao[6:].split('.')
            card_num = splitted_cartao[3][:4]
            card_name = splitted_cartao[3][4:]

    return mes, ano, card_num, card_name

def get_transaction_value(line):
    '''
    Gets a transaction line and returns the value, which usually is on the right side of it
    Also converts it to float
    '''
    idx = line.rfind(" ") - 2

    value = float(line[idx:].strip().replace(".", "").replace(",", ".").replace(" ", ""))

    return value

def is_transaction_line(line):
    '''
    Checks if a line contains a transaction. All transaction lines starts with DD/MM. However,
    we don't want to get the lines with annual fee, so we discard it
    '''
    if re.findall("\d\d/\d\d", line[:5]) != []:
        return not line.find("ANUIDADE") > 0
    return False

def get_category(line):
    '''
    Itau categorizes the transaction in a new line. The line always starts with the category.
    So, the function checks if the line is a category and returns it. 
    Returns empty string if the line is not a category
    '''
    for category in _VALID_CATEGORIES:
        size = len(category)

        if(line[:size] == category):
            return category

    return ""

def is_next_month(line):
    '''
    After all the transactions, Itau adds a summary of installments due next month
    We need to discard those, as they will be considered next month

    The line starts with "compras parceladas - próximas faturas", so that will be our marker
    '''
    text_to_look = 'compras parceladas - próximas faturas'
    text_size = len(text_to_look)

    return text_to_look == line[:text_size].lower()

def get_second_column_index(line):
    '''
    The document have 2 columns and the position varies. However, the page always starts
    with some terms. The same terms are used on the first and second col, thats why
    the rfind is used together with a threshold check. If the index is lesser then 40
    then the term found was on the first column
    This function search these terms and return the index that the second col starts
    '''
    idx_second_col = line.rfind("Lançamentos")
    
    if idx_second_col < 40:
        idx_second_col = line.rfind("Compras")

    if idx_second_col < 40:
        idx_second_col = line.rfind("Pagamento")

    if idx_second_col < 40:
        idx_second_col = line.rfind("Encargos")

    if idx_second_col < 40:
        idx_second_col = line.rfind("Parcelas")

    return idx_second_col


def process_transaction_page(page, i, ret_list = []):
    '''
    Function that process all the pages containing transaction, that are all pages except page 0
    and last page.

    The main objective is to put all the transactions, followed by their category, in a ordered
    list
    '''
    page_proc = page.split("\n")

    lista_1 = []
    lista_2 = []

    stop_add_2 = False
    ignore_list_2 = False

    for idx, line in enumerate(page_proc):
        #First line, must check for column position
        if idx == 0:
            # If the line is shorter than 70 digitss, then is has a single column and no
            # transaction info
            if len(line) < 70:
                return ret_list, True

            idx_second_col = get_second_column_index(line)

        first_column = line[:idx_second_col].strip()
        last_column = line[idx_second_col:].strip()

        # If the first column is presenting the next month installments, then everything on
        # second column is due next month. Hence, we need to ignore it.
        if is_next_month(first_column):
            ignore_list_2 = True
            break

        if (is_transaction_line(first_column) or get_category(first_column) != ""):
            lista_1.append(first_column)

        # if the second column is presenting next month instaallments, then we need to stop adding
        # on the transaction list.       
        if is_next_month(last_column):
            stop_add_2 = True

        if ((not stop_add_2) and (is_transaction_line(last_column) or get_category(last_column) != "")): 
            lista_2.append(last_column)

    # Flatten and add all traansactions ordered in a final list
    for transac in lista_1:
        ret_list.append(transac)
    
    if not ignore_list_2:
        for transac in lista_2:
            ret_list.append(transac)

    # The ignore or stop is returned so we can stop processing the transaction pages
    # If any column is presenting next month installments, then all the next transaction
    # pages will only contain next month installments
    return ret_list, ignore_list_2 or stop_add_2

def summarize_values(pd_csv, card_num, card_name):
    '''
    Using the pandas returned from process_file, calculate some summarizations and save
    as csv file
    '''
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

def process_file(filename):
    '''
    Reads a pdf file, process it and returns a pandas dataframe containing the date, category and value.
    '''
    print("Processing: {}".format(filename))

    pdf, pg_end = pdf_to_text(filename)

    # Move the pdf to the 'Processed' folder
    rename(filename, "{}/{}".format("Processed", filename))
    transaction_list = []
    stop_processing = False

    for idx, page in enumerate(pdf):
            if idx == 0:
                mes_emissao, ano_emissao, card_num, card_name = process_first_page(page)
            elif idx == pg_end:
                break
            else:
                if stop_processing:
                    continue

                transaction_list, stop_processing = process_transaction_page(page, idx, transaction_list)

    i = 0
    listaFinal = []

    while i < len(transaction_list):
        if i+1 >= len(transaction_list):
            break

        valor = get_transaction_value(transaction_list[i])
        categoria = get_category(transaction_list[i+1])
        listaFinal.append(["{}/{}".format(ano_emissao, mes_emissao), categoria, valor])

        i += 2

    pd_csv = pd.DataFrame(listaFinal, columns=["AnoMes", "Categoria", "Valor"])
    return pd_csv, card_num, card_name


if __name__ == '__main__':
    for file in listdir("."):
        if file[-3:] != "pdf":
            continue

        pd_csv, card_num, card_name = process_file(file)
        summarize_values(pd_csv, card_num, card_name)
