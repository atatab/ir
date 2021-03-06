import os
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
import chromedriver_binary  # do not remove
from selenium.common.exceptions import NoSuchElementException

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.selenium import configure_driver


class CrawlerCei():

    def __init__(self, headless=False, directory=None, debug=False):
        self.BASE_URL = 'https://cei.b3.com.br/'
        self.driver = configure_driver(headless)
        self.directory = directory
        self.debug = debug

    def busca_trades(self):
        try:
            self.driver.get(self.BASE_URL)
            self.__login()
            df = self.__abre_consulta_trades()
            return self.__converte_dataframe_para_formato_padrao(df)
        except Exception as ex:
            raise ex
        finally:
            self.driver.quit()

    def __login(self):
        if self.debug: self.driver.save_screenshot(self.directory + r'01.png')
        txt_login = self.driver.find_element_by_id('ctl00_ContentPlaceHolder1_txtLogin')
        txt_login.clear()
        txt_login.send_keys(os.environ['CPF'])

        txt_senha = self.driver.find_element_by_id('ctl00_ContentPlaceHolder1_txtSenha')
        txt_senha.clear()
        txt_senha.send_keys(os.environ['SENHA_CEI'])

        if self.debug: self.driver.save_screenshot(self.directory + r'02.png')

        btn_logar = self.driver.find_element_by_id('ctl00_ContentPlaceHolder1_btnLogar')
        btn_logar.click()

        WebDriverWait(self.driver, 60).until(EC.visibility_of_element_located((By.ID, 'objGrafPosiInv')))

        if self.debug: self.driver.save_screenshot(self.directory + r'03.png')

    def __abre_consulta_trades(self):
        class AnyEc:
            """ Use with WebDriverWait to combine expected_conditions
                in an OR.
            """
            def __init__(self, *args):
                self.ecs = args
            def __call__(self, driver):
                for fn in self.ecs:
                    try:
                        if fn(driver): return True
                    except:
                        pass

        def consultar_click(driver):
            btn_consultar = driver.find_element_by_id('ctl00_ContentPlaceHolder1_btnConsultar')
            btn_consultar.click()
        
        def not_disabled(driver):
            try:
                driver.find_element_by_id('ctl00_ContentPlaceHolder1_ddlAgentes')
            except NoSuchElementException:
                return False
            return driver.find_element_by_id('ctl00_ContentPlaceHolder1_ddlAgentes').get_attribute(
                "disabled") is None
        df = []

        self.driver.get(self.BASE_URL + 'negociacao-de-ativos.aspx')
        if self.debug: self.driver.save_screenshot(self.directory + r'04.png')

        from selenium.webdriver.support.select import Select
        ddlAgentes = Select(self.driver.find_element_by_id('ctl00_ContentPlaceHolder1_ddlAgentes'))
        for i in range(1,len(ddlAgentes.options)):
            ddlAgentes = Select(self.driver.find_element_by_id('ctl00_ContentPlaceHolder1_ddlAgentes'))
            ddlAgentes.select_by_index(i)
            consultar_click(self.driver)

            if self.debug: self.driver.save_screenshot(self.directory + r'05.png')
            WebDriverWait(self.driver, 30).until(AnyEc(
                EC.visibility_of_element_located((By.ID, 'ctl00_ContentPlaceHolder1_rptAgenteBolsa_ctl00_rptContaBolsa_ctl00_pnAtivosNegociados')),
                EC.visibility_of_element_located((By.ID, 'CEIMessageDIV'))))
            if self.debug: self.driver.save_screenshot(self.directory + r'06.png')

            # checa se existem trades para essa corretora
            aviso = self.driver.find_element_by_id("CEIMessageDIV")
            if aviso.text == 'Não foram encontrados resultados para esta pesquisa.\n×' :
                consultar_click(self.driver)
                WebDriverWait(self.driver, 60).until(not_disabled)
                continue

            df.append(self.__converte_trades_para_dataframe())
            consultar_click(self.driver)
            WebDriverWait(self.driver, 60).until(not_disabled)
        return pd.concat(df)

    def __converte_trades_para_dataframe(self):

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        top_div = soup.find('div', {'id': 'ctl00_ContentPlaceHolder1_rptAgenteBolsa_ctl00_rptContaBolsa_ctl00_pnAtivosNegociados'})

        table = top_div.find(lambda tag: tag.name == 'table')

        df = pd.read_html(str(table), decimal=',', thousands='.')[0]

        df = df.dropna(subset=['Mercado'])
        return df

    def __converte_dataframe_para_formato_padrao(self, df):
        df = df.rename(columns={'Código Negociação': 'ticker',
                                'Compra/Venda': 'operacao',
                                'Quantidade': 'qtd',
                                'Data do Negócio': 'data',
                                'Preço (R$)': 'preco',
                                'Valor Total(R$)': 'valor'})

        from src.stuff import calculate_add

        def formata_compra_venda(operacao):
            if operacao == 'V':
                return 'Venda'
            else:
                return 'Compra'

        def remove_fracionado_ticker(ticker):
            return ticker[:-1] if ticker.endswith('F') else ticker

        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['data'] = df['data'].dt.date
        df['ticker'] = df.apply(lambda row: remove_fracionado_ticker(row.ticker), axis=1)
        df['operacao'] = df.apply(lambda row: formata_compra_venda(row.operacao), axis=1)
        df['qtd_ajustada'] = df.apply(lambda row: calculate_add(row), axis=1)

        df['taxas'] = 0.0
        df['aquisicao_via'] = 'HomeBroker'

        df.drop(columns=['Mercado', 
                         'Prazo/Vencimento', 
                         'Especificação do Ativo',
                         'Fator de Cotação'], inplace=True)
        return df