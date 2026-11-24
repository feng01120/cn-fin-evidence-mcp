# -*- coding: utf-8 -*-
"""科目映射：把年报原生科目名映射为稳定指标键。"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class MetricDef:
    key: str
    name: str
    statement: str
    aliases: tuple
    unit: str = '元'


BALANCE = '合并资产负债表'
INCOME = '合并利润表'
CASH = '合并现金流量表'

METRICS: List[MetricDef] = [
    # 资产负债表
    MetricDef('cash', '货币资金', BALANCE, ('货币资金',)),
    MetricDef('accounts_receivable', '应收账款', BALANCE, ('应收账款',)),
    MetricDef('inventory', '存货', BALANCE, ('存货',)),
    MetricDef('total_current_assets', '流动资产合计', BALANCE, ('流动资产合计',)),
    MetricDef('total_noncurrent_assets', '非流动资产合计', BALANCE, ('非流动资产合计',)),
    MetricDef('total_assets', '资产总计', BALANCE, ('资产总计',)),
    MetricDef('total_current_liabilities', '流动负债合计', BALANCE, ('流动负债合计',)),
    MetricDef('total_noncurrent_liabilities', '非流动负债合计', BALANCE, ('非流动负债合计',)),
    MetricDef('total_liabilities', '负债合计', BALANCE, ('负债合计',)),
    MetricDef('equity_parent', '归属于母公司所有者权益合计', BALANCE, ('归属于母公司所有者权益合计', '归属于母公司所有者权益', '归属于母公司股东权益合计')),
    MetricDef('total_equity', '所有者权益合计', BALANCE, ('所有者权益合计', '股东权益合计', '所有者权益（或股东权益）合计')),
    MetricDef('total_liabilities_equity', '负债和所有者权益总计', BALANCE, ('负债和所有者权益总计', '负债和股东权益总计', '负债和所有者权益（或股东权益）总计')),
    # 利润表
    MetricDef('total_revenue', '营业总收入', INCOME, ('营业总收入',)),
    MetricDef('revenue', '营业收入', INCOME, ('营业收入',)),
    MetricDef('total_cost', '营业总成本', INCOME, ('营业总成本',)),
    MetricDef('cost_of_revenue', '营业成本', INCOME, ('营业成本',)),
    MetricDef('taxes_surcharges', '税金及附加', INCOME, ('税金及附加',)),
    MetricDef('selling_expense', '销售费用', INCOME, ('销售费用',)),
    MetricDef('admin_expense', '管理费用', INCOME, ('管理费用',)),
    MetricDef('rd_expense', '研发费用', INCOME, ('研发费用',)),
    MetricDef('finance_expense', '财务费用', INCOME, ('财务费用',)),
    MetricDef('operating_profit', '营业利润', INCOME, ('营业利润',)),
    MetricDef('total_profit', '利润总额', INCOME, ('利润总额',)),
    MetricDef('net_profit', '净利润', INCOME, ('净利润',)),
    MetricDef('net_profit_parent', '归属于母公司股东的净利润', INCOME, ('归属于母公司股东的净利润', '归属于母公司所有者的净利润')),
    MetricDef('basic_eps', '基本每股收益', INCOME, ('基本每股收益',), '元/股'),
    # 现金流量表
    MetricDef('sales_cash', '销售商品、提供劳务收到的现金', CASH, ('销售商品、提供劳务收到的现金',)),
    MetricDef('cfo', '经营活动产生的现金流量净额', CASH, ('经营活动产生的现金流量净额',)),
    MetricDef('cfi', '投资活动产生的现金流量净额', CASH, ('投资活动产生的现金流量净额', '投资活动使用的现金流量净额', '投资活动产生/（使用）的现金流量净额')),
    MetricDef('cff', '筹资活动产生的现金流量净额', CASH, ('筹资活动产生的现金流量净额', '筹资活动使用的现金流量净额', '筹资活动产生/（使用）的现金流量净额', '筹资活动使用/产生的现金流量净额')),
    MetricDef('fx_effect', '汇率变动对现金及现金等价物的影响', CASH, ('汇率变动对现金及现金等价物的影响', '汇率变动对现金及现金等价物的')),
    MetricDef('net_cash_increase', '现金及现金等价物净增加额', CASH, ('现金及现金等价物净增加额', '现金及现金等价物净减少额', '现金及现金等价物净增加/(减少)额')),
    MetricDef('beginning_cash', '期初现金及现金等价物余额', CASH, ('期初现金及现金等价物余额', '年初现金及现金等价物余额')),
    MetricDef('ending_cash', '期末现金及现金等价物余额', CASH, ('期末现金及现金等价物余额', '年末现金及现金等价物余额')),
]

OPTIONAL_METRICS = {'total_revenue', 'total_cost', 'finance_expense'}
REQUIRED_METRICS = [m.key for m in METRICS if m.key not in OPTIONAL_METRICS]

BY_STATEMENT = {}
BY_KEY = {}
for m in METRICS:
    BY_STATEMENT.setdefault(m.statement, []).append(m)
    BY_KEY[m.key] = m

# 合并报表的起止标题（遇到下一张报表标题即停止）
STATEMENT_ORDER = [BALANCE, INCOME, CASH]
STOP_TITLES = {
    BALANCE: ('母公司资产负债表', '公司资产负债表', INCOME),
    INCOME: ('母公司利润表', '公司利润表', CASH),
    CASH: ('母公司现金流量表', '公司现金流量表', '母公司所有者权益变动表',
           '公司所有者权益变动表', '合并所有者权益变动表', '合并股东权益变动表',
           '合并及公司股东权益变动表'),
}
