import sys
import numpy as np
import pandas as pd
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from pathlib import Path

class JackeryVisualizer(QtWidgets.QMainWindow):
    """
    Jackery APIで保存したCSVファイル (jackery_log.csv) のデータを可視化するツール
    
    機能:
    - X軸は日時, Y軸はチェックボックスで選択した各ステータス値
    - マウスによるX軸(時間軸)のスクロール・拡大縮小
    - 右メニューから表示する系列を動的に選択可能
    """

    def __init__(self, csv_file="jackery_log.csv"):
        super().__init__()
        # スクリプトのディレクトリを基準にCSVパスを設定
        base_dir = Path(__file__).parent
        self.csv_file = base_dir / csv_file
        
        self.data_df = None
        self.plot_items = {}
        self.checkboxes = {}
        
        self.init_data()
        self.init_ui()
        
    def init_data(self):
        """CSVファイルからデータを読み込み"""
        if not self.csv_file.exists():
            print(f"[{self.csv_file}] が見つかりません。")
            self.data_df = pd.DataFrame()
            return
            
        try:
            self.data_df = pd.read_csv(self.csv_file)
            self.data_df['Timestamp'] = pd.to_datetime(self.data_df['Timestamp'])
            
            # タイムゾーン情報を持たない場合はJST(Asia/Tokyo)を付与する
            if self.data_df['Timestamp'].dt.tz is None:
                self.data_df['Timestamp'] = self.data_df['Timestamp'].dt.tz_localize('Asia/Tokyo')
            
            # boolean/文字列として読み込まれたカラムを数値に変換 (OutputAC, OutputDC等)
            for col in ['OutputAC', 'OutputDC']:
                if col in self.data_df.columns:
                    self.data_df[col] = self.data_df[col].astype(int)
        except Exception as e:
            print(f"データ読み込みエラー: {e}")
            self.data_df = pd.DataFrame()
            
    def init_ui(self):
        """UIの初期化ダイアログ"""
        self.setWindowTitle('Jackery Log Visualizer')
        self.resize(900, 480)
        
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        # 全体レイアウト (左：プロット、右：コントロール)
        main_layout = QtWidgets.QHBoxLayout(central_widget)
        
        # ---------------------------------------------
        # グラフ描画領域 (PyQtGraph)
        # ---------------------------------------------
        self.plot_widget = pg.PlotWidget()
        main_layout.addWidget(self.plot_widget, stretch=4)
        
        # X軸を時間軸（DateTime）に設定
        axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget.setAxisItems({'bottom': axis})
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        self.plot_widget.setLabel('bottom', "Date & Time")
        
        # マウス操作の設定 (X軸のみズーム/パンを許可、Y軸は自動追従)
        self.plot_widget.setMouseEnabled(x=True, y=False)
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)
        self.plot_widget.setAutoVisible(y=True)
        
        # ---------------------------------------------
        # コントロール領域（チェックボックス等）
        # ---------------------------------------------
        control_layout = QtWidgets.QVBoxLayout()
        
        label = QtWidgets.QLabel("表示するステータス値")
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        control_layout.addWidget(label)
        
        # スクロールエリア（項目が多い場合に備えて）
        scroll_area = QtWidgets.QScrollArea()
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        
        if not self.data_df.empty:
            columns_to_plot = [col for col in self.data_df.columns if col != 'Timestamp']
            
            for i, col in enumerate(columns_to_plot):
                cb = QtWidgets.QCheckBox(col)
                # デフォルトでチェックを入れる項目
                if col in ['Battery(%)', 'BatteryTemp(C)', 'InputPower(W)', 'OutputPower(W)']:
                    cb.setChecked(True)
                    
                cb.stateChanged.connect(self.update_plots)
                scroll_layout.addWidget(cb)
                
                # 自動で異なる色を割り当てる
                color = pg.intColor(i, hues=len(columns_to_plot))
                self.checkboxes[col] = {
                    'checkbox': cb,
                    'color': color
                }
        else:
            no_data_label = QtWidgets.QLabel("データがありません")
            scroll_layout.addWidget(no_data_label)
            
        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumWidth(250)
        
        control_layout.addWidget(scroll_area)
        
        # 更新ボタン
        reload_btn = QtWidgets.QPushButton("データの再読み込み (Reload)")
        reload_btn.setMinimumHeight(40)
        reload_btn.clicked.connect(self.reload_data)
        control_layout.addWidget(reload_btn)
        
        main_layout.addLayout(control_layout, stretch=1)
        
        # 初回の描画処理
        self.update_plots()
        
    def reload_data(self):
        """CSVファイルを再度読み込んでグラフを更新"""
        self.init_data()
        if not self.data_df.empty:
            self.update_plots()
            
    def update_plots(self):
        """チェックボックスの状態に合わせてグラフを再描画"""
        self.plot_widget.clear()
        
        if self.data_df.empty:
            return
            
        # Timestamp配列をUnix時間に変換してnumpy配列としてPyQtGraphへ渡す
        timestamps = np.array([ts.timestamp() for ts in self.data_df['Timestamp']])
        
        for col, info in self.checkboxes.items():
            if info['checkbox'].isChecked():
                y_data = self.data_df[col].values
                
                # ペン(色と太さ)の設定
                pen = pg.mkPen(color=info['color'], width=2)
                
                # プロットの追加
                self.plot_widget.plot(
                    x=timestamps, 
                    y=y_data, 
                    pen=pen,
                    name=col
                )

def main():
    app = QtWidgets.QApplication(sys.argv)
    viewer = JackeryVisualizer()
    viewer.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
